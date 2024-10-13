"""Module for cloudinary api services"""

import re
from fractions import Fraction
import os
import io
from PIL import Image, ImageFile
from PIL.ExifTags import TAGS
import cloudinary
import cloudinary.uploader
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
    else:
        return f"{int(value)}s"


def clean_software_tag(text: str) -> str:
    """Removes unnecessary version information from the software tag"""
    if "Adobe" in text:
        match = re.search(r"Lightroom Classic \d+\.\d+", text)
        if match:
            return match.group(0)
    else:
        match = re.search(r"Ver\.? ?(\d+\.\d+)|Ver(\d+\.\d+)", text)
        if match:
            version_number = match.group(1) or match.group(2)
            return str(float(version_number))
    return text


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
    software_version = clean_software_tag(exif_clean["Software"])
    if "Lightroom" in software_version:
        exif_clean["Software"] = software_version
    else:
        exif_clean["Software"] = (
            f"{exif_clean["Model"].replace("NIKON ", "")} Ver. {software_version}"
        )
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


def image_to_bytesio(image: Image.Image, format: str = "JPEG") -> io.BytesIO:
    """Convert a Pillow Image to a BytesIO object for upload"""
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format=format, exif=image.info.get("exif"))
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


def get_all_images(folder: str) -> dict:
    """Get all images in a specified folder"""

    return cloudinary.search.resources(
        type="upload", expression=f"folder:{folder}", max_results=500
    )


def update_image(public_id: str, context: dict) -> dict:
    """Update image context in cloudinary"""
    context_str = "|".join(f"{key}={value}" for key, value in context.items())
    return cloudinary.uploader.explicit(public_id, context=context_str)


def upload_folder(folder_path: str):
    """Upload all images in a folder to cloudinary"""
    image_files = get_image_files(folder_path)
    cdn_folder = os.path.basename(folder_path)

    for image_path in image_files:
        public_id = os.path.basename(image_path)
        image = Image.open(image_path)

        exif = get_image_exif(image)
        context = filter_exif(exif)
        compressed_image = reduce_image_size(image)
        converted_image = image_to_bytesio(compressed_image)
        upload_image(converted_image, cdn_folder, public_id, context)


# upload_folder("/Users/melihavci/Desktop/Website/Test_Auto_Upload")
