import pytest
from pathlib import Path

from ba_modding_toolkit.bundle import Bundle
from ba_modding_toolkit.core import get_unity_platform_info
from ba_modding_toolkit.cli.taps import UpdateTap
from ba_modding_toolkit.cli.handlers import handle_update
from conftest import has_mod_update_samples


@pytest.mark.skipif(
    not has_mod_update_samples(),
    reason="old_mod.bundle AND new_original.bundle ARE REQUIRED"
)
class TestUpdateCommand:
    def test_update_basic(
        self,
        old_mod_bundle_path: Path,
        new_original_bundle_path: Path,
        tmp_path: Path,
    ):
        """测试基本的 update 功能"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        args = UpdateTap().parse_args([
            str(old_mod_bundle_path),
            "--target", str(new_original_bundle_path),
            "--output-dir", str(output_dir),
            "--no-crc",
            "--compression", "none",
        ])

        handle_update(args)

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) > 0

        for output_file in output_files:
            bundle = Bundle.load(output_file)
            assert not bundle.is_empty(), f"Failed to load output bundle: {output_file}"

    def test_update_with_asset_types(
        self,
        old_mod_bundle_path: Path,
        new_original_bundle_path: Path,
        tmp_path: Path,
    ):
        """测试指定资源类型的 update"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        args = UpdateTap().parse_args([
            str(old_mod_bundle_path),
            "--target", str(new_original_bundle_path),
            "--output-dir", str(output_dir),
            "--asset-types", "Texture2D", "TextAsset",
            "--no-crc",
            "--compression", "none",
        ])

        handle_update(args)

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) > 0

    def test_update_output_content(
        self,
        old_mod_bundle_path: Path,
        new_original_bundle_path: Path,
        tmp_path: Path,
    ):
        """测试 update 后的输出内容可以被加载"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        args = UpdateTap().parse_args([
            str(old_mod_bundle_path),
            "--target", str(new_original_bundle_path),
            "--output-dir", str(output_dir),
            "--no-crc",
            "--compression", "none",
        ])

        handle_update(args)

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) > 0

        for output_file in output_files:
            bundle = Bundle.load(output_file)
            assert not bundle.is_empty(), f"Failed to load output bundle: {output_file}"

    def test_update_metadata_consistency(
        self,
        old_mod_bundle_path: Path,
        new_original_bundle_path: Path,
        tmp_path: Path,
    ):
        """测试 update 后元数据保持一致"""
        original_platform, original_version = get_unity_platform_info(new_original_bundle_path)

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        args = UpdateTap().parse_args([
            str(old_mod_bundle_path),
            "--target", str(new_original_bundle_path),
            "--output-dir", str(output_dir),
            "--no-crc",
            "--compression", "none",
        ])

        handle_update(args)

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) > 0

        for output_file in output_files:
            bundle = Bundle.load(output_file)
            assert not bundle.is_empty(), f"Failed to load output bundle: {output_file}"
            updated_platform, updated_version = bundle.platform_info
            assert updated_platform == original_platform
            assert updated_version == original_version
