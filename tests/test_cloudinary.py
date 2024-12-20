"""Test module for cloudinary_service.py"""

from PIL import Image
import app.cloudinary_service as cs

ZF_IMAGE = "tests/test_data/DSC_0234.jpg"
Z6_IMAGE = "tests/test_data/DSC_2506.jpg"
XT4_IMAGE = "tests/test_data/DSCF3503.jpg"
XT4_LR_IMAGE = "tests/test_data/DSCF3256.jpg"


def test_get_image_exif():
    """Test reduce_image_size function"""
    image = Image.open(ZF_IMAGE)
    exif = cs.get_image_exif(image)

    assert exif["Model"] == "NIKON Z f"


def test_filter_exif():
    """Test filter_exif function"""
    image = Image.open(ZF_IMAGE)
    exif = cs.get_image_exif(image)

    filtered = cs.filter_exif(exif)

    for key, value in filtered.items():
        print(key, value)


def test_image_files():
    """Test get_image_files function"""
    folder = "/Users/melihavci/Desktop/Website/Monochrome"
    files = cs.get_image_files(folder)
    assert len(files) > 0
