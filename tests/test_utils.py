import pytest
from pathlib import Path
from PIL import Image

from ba_modding_toolkit.utils import (
    bleed_image,
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


class TestImageUtils:
    def test_bleed_image_basic(self):
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
        result = bleed_image(img)
        
        assert result.size == img.size
        assert result.mode == "RGBA"

    def test_bleed_image_preserves_alpha(self):
        img = Image.new("RGBA", (50, 50), (0, 255, 0, 128))
        original_alpha = img.getchannel("A")
        
        result = bleed_image(img)
        result_alpha = result.getchannel("A")
        
        assert list(original_alpha.getdata()) == list(result_alpha.getdata())

    def test_bleed_image_alpha_threshold(self):
        """alpha 不超过阈值的像素应被邻居颜色覆盖，alpha 通道保持原样"""
        img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
        for y in range(8):
            for x in range(4):
                img.putpixel((x, y), (255, 0, 0, 255))
            img.putpixel((4, y), (0, 0, 0, 3))  # 紧邻不透明区域、alpha 极低的黑点

        r, g, b, a = bleed_image(img, threshold=5).getpixel((4, 4))
        assert a == 3
        assert r > 200 and (g, b) == (0, 0), "低 alpha 像素的 RGB 应被扩散覆盖"

        # 阈值为 0 时只处理完全透明像素，该像素保持原色
        assert bleed_image(img, threshold=0).getpixel((4, 4)) == (0, 0, 0, 3)

    def test_bleed_image_no_transparent_pixels(self):
        img = Image.new("RGBA", (10, 10), (255, 255, 255, 255))
        result = bleed_image(img)
        
        assert result == img