import pytest
from pathlib import Path

from ba_modding_toolkit.core import (
    process_mod_update,
    process_asset_extraction,
    SaveOptions,
)
from ba_modding_toolkit.bundle import Bundle
from conftest import has_mod_update_samples, compare_directory_assets

MSE_THRESHOLD = 20.0

@pytest.mark.skipif(
    not has_mod_update_samples(),
    reason="old_mod.bundle AND new_original.bundle ARE REQUIRED"
)
class TestModUpdate:
    def test_mod_update_basic(
        self,
        old_mod_bundle_paths: list[Path],
        new_original_bundle_paths: list[Path],
        tmp_path: Path,
    ):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        save_options = SaveOptions(
            perform_crc=False,
            compression="none",
        )
        
        success, msg, _ = process_mod_update(
            source_paths=old_mod_bundle_paths,
            target_paths=new_original_bundle_paths,
            output_dir=output_dir,
            asset_types_to_replace={"Texture2D", "TextAsset"},
            save_options=save_options,
        )
        
        assert success is True, msg
        
        # 验证输出文件数量匹配
        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) == len(new_original_bundle_paths)

        for output_file in output_files:
            bundle = Bundle.load(output_file)
            assert not bundle.is_empty()

    def test_mod_update_metadata_consistency(
        self,
        old_mod_bundle_paths: list[Path],
        new_original_bundle_paths: list[Path],
        tmp_path: Path,
    ):
        
        new_original_bundle = Bundle.load(new_original_bundle_paths[0])
        original_platform, original_version = new_original_bundle.platform_info
        
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        save_options = SaveOptions(
            perform_crc=False,
            compression="none",
        )
        
        success, msg, _ = process_mod_update(
            source_paths=old_mod_bundle_paths,
            target_paths=new_original_bundle_paths,
            output_dir=output_dir,
            asset_types_to_replace={"Texture2D", "TextAsset"},
            save_options=save_options,
        )
        
        assert success is True, msg
        
        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) == len(new_original_bundle_paths)

        for output_file in output_files:
            updated_bundle = Bundle.load(output_file)
            updated_platform, updated_version = updated_bundle.platform_info

            assert updated_platform == original_platform
            assert updated_version == original_version

    def test_mod_update_content(
        self,
        old_mod_bundle_paths: list[Path],
        new_original_bundle_paths: list[Path],
        tmp_path: Path,
    ):
        # 提取旧 Mod 的资源用于对比
        old_extract_dir = tmp_path / "old_extracted"
        old_extract_dir.mkdir()
        
        process_asset_extraction(
            bundle_path=old_mod_bundle_paths[0],
            output_dir=old_extract_dir,
            asset_types_to_extract={"Texture2D"},
        )
        
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        save_options = SaveOptions(
            perform_crc=True,
            compression="none",
        )
        
        success, msg, _ = process_mod_update(
            source_paths=old_mod_bundle_paths,
            target_paths=new_original_bundle_paths,
            output_dir=output_dir,
            asset_types_to_replace={"Texture2D"},
            save_options=save_options,
        )
        
        assert success is True, msg
        
        # 提取更新后的资源进行对比
        updated_bundle = output_dir / new_original_bundle_paths[0].name
        new_extract_dir = tmp_path / "new_extracted"
        new_extract_dir.mkdir()
        
        process_asset_extraction(
            bundle_path=updated_bundle,
            output_dir=new_extract_dir,
            asset_types_to_extract={"Texture2D", "TextAsset"},
        )
        
        compare_directory_assets(old_extract_dir, new_extract_dir, MSE_THRESHOLD)