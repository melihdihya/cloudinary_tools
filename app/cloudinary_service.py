"""Module for cloudinary api services"""

import re
import base64
from fractions import Fraction
import os
import io
import requests
import cloudinary
from loguru import logger
from PIL import Image, ImageFile
from PIL.ExifTags import TAGS
import dotenv

MAX_FILE_SIZE = 10_485_760
EXPOSURE_PROGRAM = {
    0: "Not defined",
    1: "Manual",
    2: "Program AE",
    3: "Aperture-priority AE",
    4: "Shutter-priority AE",
    5: "Creative (slow speed)",
    6: "Action (high speed)",
    7: "Portrait",
    8: "Landscape",
}
dotenv.load_dotenv()
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)


def get_image_files(folder_path: str) -> list:
    """Get a list of full paths of all image files in the specified folder."""
    image_extensions = (
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".tiff",
        ".webp",
    )
    image_files = []
    for filename in os.listdir(folder_path):
        if filename.lower().endswith(image_extensions):
            full_path = os.path.join(folder_path, filename)
            image_files.append(full_path)
    return image_files


def convert_shutter_speed(value: float) -> str:
    """Convert shutter speed to fraction"""
    if value < 1:
        return f"{Fraction(value).limit_denominator()}s"

    return f"{int(value)}s"


def clean_software_tag(exif_dict: dict) -> dict:
    """Removes unnecessary version information from the software tag"""
    software_version = None
    if "Adobe" in exif_dict["Software"]:
        match = re.search(r"Lightroom Classic \d+\.\d+", exif_dict["Software"])
        if match:
            software_version = match.group(0)
    else:
        match = re.search(r"Ver\.? ?(\d+\.\d+)|Ver(\d+\.\d+)", exif_dict["Software"])
        if match:
            version_number = match.group(1) or match.group(2)
            software_version = str(float(version_number))

    if "Lightroom" in software_version:
        exif_dict["Software"] = software_version
    else:
        exif_dict["Software"] = (
            f"{exif_dict["Model"].replace("NIKON ", "")} Ver. {software_version}"
        )
    return exif_dict


def get_image_exif(image: ImageFile) -> dict:
    """Get exif data from image"""
    exif_dict = {}
    exif_data = image._getexif()
    if exif_data:
        exif_dict = {TAGS.get(tag, tag): value for tag, value in exif_data.items()}
    return exif_dict


def filter_exif(exif: dict) -> dict:
    """Filter exif data"""
    relevant_tags = [
        "Model",
        "LensModel",
        "FocalLengthIn35mmFilm",
        "FNumber",
        "ExposureTime",
        "ISOSpeedRatings",
        "ExposureProgram",
        "Software",
        "DateTimeOriginal",
    ]
    exif_clean = {
        key: value
        for key, value in exif.items()
        if key in relevant_tags and value is not None
    }
    exif_clean["ExposureProgram"] = EXPOSURE_PROGRAM.get(
        exif_clean["ExposureProgram"], "Not defined"
    )
    exif_clean["FocalLengthIn35mmFilm"] = f"{exif_clean["FocalLengthIn35mmFilm"]}mm"
    exif_clean["ExposureTime"] = convert_shutter_speed(
        float(exif_clean["ExposureTime"])
    )
    exif_clean = clean_software_tag(exif_clean)
    exif_clean["ISO"] = exif_clean.pop("ISOSpeedRatings")
    exif_clean["FocalLengthIn35mmFormat"] = exif_clean.pop("FocalLengthIn35mmFilm")

    return exif_clean


def reduce_image_size(image: Image.Image, max_size: int = MAX_FILE_SIZE) -> Image.Image:
    """Reduce image size to maximum allowed by Cloudinary."""

    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format="JPEG", exif=image.info.get("exif"))
    img_byte_arr.seek(0)
    current_size = img_byte_arr.getbuffer().nbytes

    if current_size > max_size:
        quality = 95
        while current_size > max_size and quality > 0:
            img_byte_arr = io.BytesIO()
            image.save(
                img_byte_arr,
                format="JPEG",
                quality=quality,
                exif=image.info.get("exif"),
            )
            img_byte_arr.seek(0)
            current_size = img_byte_arr.getbuffer().nbytes
            quality -= 5
        image = Image.open(img_byte_arr)
    return image


def image_to_bytesio(image: Image.Image, image_format: str = "JPEG") -> io.BytesIO:
    """Convert a Pillow Image to a BytesIO object for upload"""
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format=image_format, exif=image.info.get("exif"))
    img_byte_arr.seek(0)
    return img_byte_arr


def upload_image(
    file: str | io.IOBase, cdn_folder: str, public_id: str, context: dict
) -> dict:
    """Upload image to cloudinary"""

    context_str = "|".join(f"{key}={value}" for key, value in context.items())

    return cloudinary.uploader.upload(
        file,
        resource_type="image",
        folder=cdn_folder,
        context=context_str,
        use_filename=True,
        public_id=public_id,
    )


def get_cdn_images(folder: str) -> dict:
    """Get all images in a specified folder"""
    results = (
        cloudinary.search.Search()
        .expression(f"folder:{folder}")
        .sort_by("public_id", "asc")
        .max_results(400)
        .execute()
    )
    return results


def get_cdn_image(public_id: str) -> dict:
    """Get image from cloudinary"""
    return cloudinary.api.resource(public_id, image_metadata=True)


def extract_exif_from_cdn_image(image: dict) -> dict:
    """Extract exif data from cloudinary image"""
    exif_clean = {
        "Model": image["image_metadata"]["Model"],
        "LensModel": image["image_metadata"]["LensModel"],
        "FocalLengthIn35mmFormat": image["image_metadata"][
            "FocalLengthIn35mmFormat"
        ].replace(" ", ""),
        "FNumber": image["image_metadata"]["FNumber"],
        "ExposureTime": f"{image["image_metadata"]["ExposureTime"]}s",
        "ISO": image["image_metadata"]["ISO"],
        "ExposureProgram": image["image_metadata"]["ExposureProgram"],
        "Software": image["image_metadata"]["Software"],
        "DateTimeOriginal": image["image_metadata"]["DateTimeOriginal"],
    }
    exif_clean = clean_software_tag(exif_clean)
    return exif_clean


def update_cdn_image(public_id: str, context: dict) -> dict:
    """Update image context in cloudinary"""
    context_str = "|".join(f"{key}={value}" for key, value in context.items())
    return cloudinary.uploader.explicit(public_id, type="upload", context=context_str)


def get_base64_image_url(public_id: str) -> str:
    """Generate base64 image url"""
    response = requests.get(
        (
            f"https://res.cloudinary.com/{os.getenv("CLOUDINARY_CLOUD_NAME")}/"
            f"image/upload/f_jpg,w_8,q_70/{public_id}.jpg"
        ),
        stream=True,
        timeout=10,
    )
    response.raise_for_status()
    img = Image.open(io.BytesIO(response.content))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=50)
    buffer.seek(0)
    base64_image = base64.b64encode(buffer.read()).decode("utf-8")
    url = f"data:image/jpeg;base64,{base64_image}"
    return url


def upload_folder(folder_path: str, cdn_folder: str = None):
    """Upload all images in a folder to cloudinary"""
    image_files = get_image_files(folder_path)
    if not cdn_folder:
        cdn_folder = os.path.basename(folder_path)

    for image_path in image_files:
        public_id = os.path.basename(image_path).replace(".JPG", "").replace(".jpg", "")
        image = Image.open(image_path)

        exif = get_image_exif(image)
        context = filter_exif(exif)
        compressed_image = reduce_image_size(image)
        converted_image = image_to_bytesio(compressed_image)
        logger.info(f"Uploading {public_id} to Cloudinary")
        upload_image(converted_image, cdn_folder, public_id, context)
        logger.info(f"Uploaded {public_id} to Cloudinary")


def update_cdn_folder(folder: str):
    """Add context to all images in a folder"""
    images = get_cdn_images(folder)
    for image in images["resources"]:
        logger.info(f"Updating {image['public_id']} in Cloudinary")
        public_id = image["public_id"]
        image_details = get_cdn_image(public_id)
        context = extract_exif_from_cdn_image(image_details)
        update_cdn_image(public_id, context)
        logger.info(f"Updated {public_id} in Cloudinary")


# Example usage:
# upload_folder("/Users/melihavci/Desktop/Website/Test_Auto_Upload")
# update_cdn_folder("Testing")
# get_base64_image_url("Test_Auto_Upload/DSC_0134.JPG")
