import pytest
import shutil
from pathlib import Path

from ba_modding_toolkit.bundle import Bundle
from ba_modding_toolkit.cli.taps import PackTap
from ba_modding_toolkit.cli.handlers import handle_asset_packing, setup_cli_logger
from conftest import has_sample_bundle, has_sample_image


@pytest.mark.skipif(
    not all([has_sample_bundle(), has_sample_image()]),
    reason="sample.bundle AND sample.png ARE REQUIRED"
)
class TestPackCommand:
    def test_pack_basic(
        self,
        sample_bundle_paths: list[Path],
        sample_image_path: Path,
        tmp_path: Path,
    ):
        """测试基本的 pack 功能（多 bundle）"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        asset_folder = tmp_path / "assets"
        asset_folder.mkdir()
        shutil.copy(sample_image_path, asset_folder / sample_image_path.name)

        # 构建多 bundle 参数
        bundle_args = ["--bundle"] + [str(p) for p in sample_bundle_paths]

        args = PackTap().parse_args(
            bundle_args + [
                "--folder", str(asset_folder),
                "--output-dir", str(output_dir),
                "--no-crc",
                "--compression", "none",
            ]
        )

        logger = setup_cli_logger()
        handle_asset_packing(args, logger)

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) == len(sample_bundle_paths), "输出文件数量应与输入 bundle 数量匹配"

        for output_file in output_files:
            bundle = Bundle.load(output_file)
            assert not bundle.is_empty(), f"Failed to load output bundle: {output_file}"

    def test_pack_output_content(
        self,
        sample_bundle_paths: list[Path],
        sample_image_path: Path,
        tmp_path: Path,
    ):
        """测试 pack 后的输出内容可以被加载"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        asset_folder = tmp_path / "assets"
        asset_folder.mkdir()
        shutil.copy(sample_image_path, asset_folder / sample_image_path.name)

        # 构建多 bundle 参数
        bundle_args = ["--bundle"] + [str(p) for p in sample_bundle_paths]

        args = PackTap().parse_args(
            bundle_args + [
                "--folder", str(asset_folder),
                "--output-dir", str(output_dir),
                "--no-crc",
                "--compression", "none",
            ]
        )

        logger = setup_cli_logger()
        handle_asset_packing(args, logger)

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) == len(sample_bundle_paths)

        for output_file in output_files:
            bundle = Bundle.load(output_file)
            assert not bundle.is_empty(), f"Failed to load output bundle: {output_file}"