from pathlib import Path
from typing import TYPE_CHECKING

from ba_modding_toolkit.core import (
    process_mod_update,
    _extract_assets_from_bundle,
    SaveOptions,
)
from ba_modding_toolkit.bundle import Bundle
from conftest import compare_directory_assets

if TYPE_CHECKING:
    from conftest import UpdateCase

MSE_THRESHOLD = 20.0

# 案例数据缺失时 conftest 参数化为空参数集，测试自动跳过
class TestModUpdate:
    def test_mod_update_basic(
        self,
        update_case: "UpdateCase",
        tmp_path: Path,
    ):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        save_options = SaveOptions(
            perform_crc=False,
            compression="none",
        )
        
        result = process_mod_update(
            source_paths=update_case.old_paths,
            target_paths=update_case.new_paths,
            output_dir=output_dir,
            asset_types_to_replace={"Texture2D", "TextAsset"},
            save_options=save_options,
        )
        
        assert result.success is True, result.message
        
        # 验证输出文件数量匹配
        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) == len(update_case.new_paths)

        for output_file in output_files:
            bundle = Bundle.load(output_file)
            assert not bundle.is_empty()

    def test_mod_update_metadata_consistency(
        self,
        update_case: "UpdateCase",
        tmp_path: Path,
    ):
        
        new_original_bundle = Bundle.load(update_case.new_paths[0])
        original_platform, original_version = new_original_bundle.platform_info
        
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        save_options = SaveOptions(
            perform_crc=False,
            compression="none",
        )
        
        result = process_mod_update(
            source_paths=update_case.old_paths,
            target_paths=update_case.new_paths,
            output_dir=output_dir,
            asset_types_to_replace={"Texture2D", "TextAsset"},
            save_options=save_options,
        )
        
        assert result.success is True, result.message
        
        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) == len(update_case.new_paths)

        for output_file in output_files:
            updated_bundle = Bundle.load(output_file)
            updated_platform, updated_version = updated_bundle.platform_info

            assert updated_platform == original_platform
            assert updated_version == original_version

    def test_mod_update_content(
        self,
        update_case: "UpdateCase",
        tmp_path: Path,
    ):
        # 提取旧 Mod 的资源用于对比
        old_extract_dir = tmp_path / "old_extracted"
        old_extract_dir.mkdir()

        _extract_assets_from_bundle([update_case.old_paths[0]], old_extract_dir, {"Texture2D"})
        
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        save_options = SaveOptions(
            perform_crc=True,
            compression="none",
        )
        
        result = process_mod_update(
            source_paths=update_case.old_paths,
            target_paths=update_case.new_paths,
            output_dir=output_dir,
            asset_types_to_replace={"Texture2D"},
            save_options=save_options,
        )
        
        assert result.success is True, result.message
        
        # 提取更新后的资源进行对比
        updated_bundle = output_dir / update_case.new_paths[0].name
        new_extract_dir = tmp_path / "new_extracted"
        new_extract_dir.mkdir()

        _extract_assets_from_bundle([updated_bundle], new_extract_dir, {"Texture2D", "TextAsset"})
        
        compare_directory_assets(old_extract_dir, new_extract_dir, MSE_THRESHOLD)