import pytest
from pathlib import Path
import shutil

from ba_modding_toolkit.core import load_bundle
from ba_modding_toolkit.cli.taps import PackTap
from ba_modding_toolkit.cli.handlers import handle_asset_packing
from conftest import has_sample_bundle, has_sample_image


@pytest.mark.skipif(
    not has_sample_bundle() or not has_sample_image(),
    reason="Sample bundle AND image files ARE REQUIRED"
)
class TestPackCommand:
    def test_pack_basic(
        self,
        sample_bundle_path: Path,
        sample_image_path: Path,
        tmp_path: Path,
    ):
        """测试基本的 pack 功能"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        asset_folder = tmp_path / "assets"
        asset_folder.mkdir()
        shutil.copy(sample_image_path, asset_folder / sample_image_path.name)

        args = PackTap().parse_args([
            "--bundle", str(sample_bundle_path),
            "--folder", str(asset_folder),
            "--output-dir", str(output_dir),
            "--no-crc",
            "--compression", "none",
        ])

        handle_asset_packing(args)

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) > 0, "No output files generated"

    def test_pack_output_content(
        self,
        sample_bundle_path: Path,
        sample_image_path: Path,
        tmp_path: Path,
    ):
        """测试 pack 后的输出内容可以被加载"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        asset_folder = tmp_path / "assets"
        asset_folder.mkdir()
        shutil.copy(sample_image_path, asset_folder / sample_image_path.name)

        args = PackTap().parse_args([
            "--bundle", str(sample_bundle_path),
            "--folder", str(asset_folder),
            "--output-dir", str(output_dir),
            "--no-crc",
            "--compression", "none",
        ])

        handle_asset_packing(args)

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) > 0

        for output_file in output_files:
            env = load_bundle(output_file)
            assert env is not None, f"Failed to load output bundle: {output_file}"
