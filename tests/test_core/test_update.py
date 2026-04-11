import pytest
from pathlib import Path

from ba_modding_toolkit.core import (
    process_mod_update,
    get_unity_platform_info,
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
        old_mod_bundle_path: Path,
        new_original_bundle_path: Path,
        tmp_path: Path,
    ):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        save_options = SaveOptions(
            perform_crc=False,
            compression="none",
        )
        
        success, msg = process_mod_update(
            old_mod_path=old_mod_bundle_path,
            new_bundle_path=new_original_bundle_path,
            output_dir=output_dir,
            asset_types_to_replace={"Texture2D", "TextAsset"},
            save_options=save_options,
        )
        
        assert success is True, msg
        
        updated_bundle = output_dir / new_original_bundle_path.name
        
        bundle = Bundle.load(updated_bundle)
        assert not bundle.is_empty()

    def test_mod_update_metadata_consistency(
        self,
        old_mod_bundle_path: Path,
        new_original_bundle_path: Path,
        tmp_path: Path,
    ):
        original_platform, original_version = get_unity_platform_info(new_original_bundle_path)
        
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        save_options = SaveOptions(
            perform_crc=False,
            compression="none",
        )
        
        success, msg = process_mod_update(
            old_mod_path=old_mod_bundle_path,
            new_bundle_path=new_original_bundle_path,
            output_dir=output_dir,
            asset_types_to_replace={"Texture2D", "TextAsset"},
            save_options=save_options,
        )
        
        assert success is True, msg
        
        updated_bundle = output_dir / new_original_bundle_path.name
        updated_platform, updated_version = get_unity_platform_info(updated_bundle)
        
        assert updated_platform == original_platform
        assert updated_version == original_version

    def test_mod_update_content(
        self,
        old_mod_bundle_path: Path,
        new_original_bundle_path: Path,
        tmp_path: Path,
    ):
        old_extract_dir = tmp_path / "old_extracted"
        old_extract_dir.mkdir()
        
        process_asset_extraction(
            bundle_path=old_mod_bundle_path,
            output_dir=old_extract_dir,
            asset_types_to_extract={"Texture2D"},
        )
        
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        save_options = SaveOptions(
            perform_crc=True,
            compression="none",
        )
        
        success, msg = process_mod_update(
            old_mod_path=old_mod_bundle_path,
            new_bundle_path=new_original_bundle_path,
            output_dir=output_dir,
            asset_types_to_replace={"Texture2D"},
            save_options=save_options,
        )
        
        assert success is True, msg
        
        updated_bundle = output_dir / new_original_bundle_path.name
        new_extract_dir = tmp_path / "new_extracted"
        new_extract_dir.mkdir()
        
        process_asset_extraction(
            bundle_path=updated_bundle,
            output_dir=new_extract_dir,
            asset_types_to_extract={"Texture2D", "TextAsset"},
        )
        
        compare_directory_assets(old_extract_dir, new_extract_dir, MSE_THRESHOLD)