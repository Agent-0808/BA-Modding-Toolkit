import pytest
from pathlib import Path
from PIL import Image

from ba_modding_toolkit.core import (
    process_asset_extraction,
)
from conftest import has_sample_bundle


@pytest.mark.skipif(
    not has_sample_bundle(),
    reason="sample.bundle IS REQUIRED"
)
class TestAssetExtraction:
    def test_extract_texture2d(self, sample_bundle_paths: list[Path], tmp_path: Path):
        output_dir = tmp_path / "extracted"
        output_dir.mkdir()
        
        success, msg = process_asset_extraction(
            bundle_path=sample_bundle_paths,
            output_dir=output_dir,
            asset_types_to_extract={"Texture2D"},
        )
        
        assert success is True, msg
        
        png_files = list(output_dir.glob("*.png"))
        assert len(png_files) > 0
        
        for png_file in png_files:
            img = Image.open(png_file)
            assert img.mode == "RGBA"

    def test_extract_textasset(self, sample_bundle_paths: list[Path], tmp_path: Path):
        output_dir = tmp_path / "extracted"
        output_dir.mkdir()
        
        success, msg = process_asset_extraction(
            bundle_path=sample_bundle_paths,
            output_dir=output_dir,
            asset_types_to_extract={"TextAsset"},
        )
        
        assert success is True, msg

    def test_extract_multiple_types(self, sample_bundle_paths: list[Path], tmp_path: Path):
        output_dir = tmp_path / "extracted"
        output_dir.mkdir()
        
        success, msg = process_asset_extraction(
            bundle_path=sample_bundle_paths,
            output_dir=output_dir,
            asset_types_to_extract={"Texture2D", "TextAsset"},
        )
        
        assert success is True, msg

    def test_extract_to_nonexistent_dir(self, sample_bundle_paths: list[Path], tmp_path: Path):
        output_dir = tmp_path / "new_dir"
        
        success, msg = process_asset_extraction(
            bundle_path=sample_bundle_paths,
            output_dir=output_dir,
            asset_types_to_extract={"Texture2D"},
        )
        
        assert success is True
        assert output_dir.exists()

    def test_extract_with_unpack_atlas(self, sample_bundle_paths: list[Path], tmp_path: Path):
        """测试启用 atlas 解包功能"""
        output_dir = tmp_path / "extracted"
        output_dir.mkdir()
        
        success, msg = process_asset_extraction(
            bundle_path=sample_bundle_paths,
            output_dir=output_dir,
            asset_types_to_extract={"TextAsset", "Texture2D"},
            enable_unpack_atlas=True,
        )
        
        assert success is True, msg
        
        # 检查 atlas 解包结果（如果 bundle 包含 atlas）
        images_dir = output_dir / "images"
        if images_dir.exists():
            # 验证解包的帧图片
            png_frames = list(images_dir.glob("*.png"))
            assert len(png_frames) > 0
            
            # 验证帧图片格式
            for png_frame in png_frames:
                img = Image.open(png_frame)
                assert img.mode == "RGBA"
