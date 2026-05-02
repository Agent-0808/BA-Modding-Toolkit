import pytest
from pathlib import Path

from ba_modding_toolkit.core import (
    process_modern_to_legacy_conversion,
    process_legacy_to_modern_conversion,
    SaveOptions,
)
from ba_modding_toolkit.bundle import Bundle
from conftest import has_legacy_format_samples


@pytest.mark.skipif(
    not has_legacy_format_samples(),
    reason="Legacy bundle AND modern bundles ARE REQUIRED"
)
class TestJpToGlobalConversion:
    def test_jp_to_global_basic(
        self,
        legacy_bundle_path: Path,
        modern_bundles_path: list[Path],
        tmp_path: Path,
    ):
        """测试基本的 JP 转 Global 功能"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        save_options = SaveOptions(
            perform_crc=False,
            compression="none",
        )

        success, msg = process_modern_to_legacy_conversion(
            legacy_bundle_path=legacy_bundle_path,
            modern_bundle_paths=modern_bundles_path,
            output_dir=output_dir,
            save_options=save_options,
            asset_types_to_replace={"Texture2D", "TextAsset"},
        )

        assert success is True, msg

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) > 0, "No output files generated"

    def test_jp_to_global_output_content(
        self,
        legacy_bundle_path: Path,
        modern_bundles_path: list[Path],
        tmp_path: Path,
    ):
        """测试 JP 转 Global 后的输出内容可以被加载"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        save_options = SaveOptions(
            perform_crc=False,
            compression="none",
        )

        success, msg = process_modern_to_legacy_conversion(
            legacy_bundle_path=legacy_bundle_path,
            modern_bundle_paths=modern_bundles_path,
            output_dir=output_dir,
            save_options=save_options,
            asset_types_to_replace={"Texture2D", "TextAsset"},
        )

        assert success is True, msg

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) > 0

        for output_file in output_files:
            bundle = Bundle.load(output_file)
            assert not bundle.is_empty(), f"Failed to load output bundle: {output_file}"


@pytest.mark.skipif(
    not has_legacy_format_samples(),
    reason="Legacy bundle AND modern bundles ARE REQUIRED"
)
class TestGlobalToJpConversion:
    def test_global_to_jp_basic(
        self,
        legacy_bundle_path: Path,
        modern_bundles_path: list[Path],
        tmp_path: Path,
    ):
        """测试基本的 Global 转 JP 功能"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        save_options = SaveOptions(
            perform_crc=False,
            compression="none",
        )

        success, msg, replaced_files = process_legacy_to_modern_conversion(
            legacy_bundle_path=legacy_bundle_path,
            modern_bundle_paths=modern_bundles_path,
            output_dir=output_dir,
            save_options=save_options,
            asset_types_to_replace={"Texture2D", "TextAsset"},
        )

        assert success is True, msg

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) > 0, "No output files generated"

    def test_global_to_jp_output_content(
        self,
        legacy_bundle_path: Path,
        modern_bundles_path: list[Path],
        tmp_path: Path,
    ):
        """测试 Global 转 JP 后的输出内容可以被加载"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        save_options = SaveOptions(
            perform_crc=False,
            compression="none",
        )

        success, msg, replaced_files = process_legacy_to_modern_conversion(
            legacy_bundle_path=legacy_bundle_path,
            modern_bundle_paths=modern_bundles_path,
            output_dir=output_dir,
            save_options=save_options,
            asset_types_to_replace={"Texture2D", "TextAsset"},
        )

        assert success is True, msg

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) > 0

        for output_file in output_files:
            bundle = Bundle.load(output_file)
            assert not bundle.is_empty(), f"Failed to load output bundle: {output_file}"

    def test_global_to_jp_replaced_files(
        self,
        legacy_bundle_path: Path,
        modern_bundles_path: list[Path],
        tmp_path: Path,
    ):
        """测试 Global 转 JP 返回的被替换文件列表"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        save_options = SaveOptions(
            perform_crc=False,
            compression="none",
        )

        success, msg, replaced_files = process_legacy_to_modern_conversion(
            legacy_bundle_path=legacy_bundle_path,
            modern_bundle_paths=modern_bundles_path,
            output_dir=output_dir,
            save_options=save_options,
            asset_types_to_replace={"Texture2D", "TextAsset"},
        )

        assert success is True, msg
        assert isinstance(replaced_files, list)
