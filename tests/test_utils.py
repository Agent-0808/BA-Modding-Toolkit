import pytest
from pathlib import Path
from PIL import Image

from ba_modding_toolkit.utils import (
    SpineUtils,
    ImageUtils,
    parse_hex_bytes,
)


class TestParseHexBytes:
    def test_parse_hex_bytes_with_prefix(self):
        result = parse_hex_bytes("0x08080808")
        assert result == b'\x08\x08\x08\x08'
        
        result = parse_hex_bytes("0XABCDEF")
        assert result == b'\xab\xcd\xef'

    def test_parse_hex_bytes_without_prefix(self):
        result = parse_hex_bytes("hello")
        assert result == b"hello"

    def test_parse_hex_bytes_empty(self):
        assert parse_hex_bytes("") is None
        assert parse_hex_bytes(None) is None

    def test_parse_hex_bytes_invalid_hex(self):
        result = parse_hex_bytes("0xGGGG")
        assert result is None

    def test_parse_hex_bytes_odd_length(self):
        result = parse_hex_bytes("0xABC")
        assert result is None


class TestSpineUtils:
    def test_get_skel_version_from_bytes(self):
        skel_header = b"spine\x00\x00\x00\x00\x00\x00\x00\x004.2.33\x00"
        version = SpineUtils.get_skel_version(skel_header)
        assert version == "4.2.33"

    def test_get_skel_version_no_version(self):
        data = b"no\x00\x00\x08version\x00\x08\x00\x08string here"
        version = SpineUtils.get_skel_version(data)
        assert version is None


class TestImageUtils:
    def test_bleed_image_basic(self):
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
        result = ImageUtils.bleed_image(img)
        
        assert result.size == img.size
        assert result.mode == "RGBA"

    def test_bleed_image_preserves_alpha(self):
        img = Image.new("RGBA", (50, 50), (0, 255, 0, 128))
        original_alpha = img.getchannel("A")
        
        result = ImageUtils.bleed_image(img)
        result_alpha = result.getchannel("A")
        
        assert list(original_alpha.getdata()) == list(result_alpha.getdata())

    def test_bleed_image_no_transparent_pixels(self):
        img = Image.new("RGBA", (10, 10), (255, 255, 255, 255))
        result = ImageUtils.bleed_image(img)
        
        assert result == img