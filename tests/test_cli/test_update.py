import pytest
from pathlib import Path

from ba_modding_toolkit.bundle import Bundle
from ba_modding_toolkit.cli.taps import UpdateTap
from ba_modding_toolkit.cli.handlers import handle_update, setup_cli_logger
from conftest import has_mod_update_samples


@pytest.mark.skipif(
    not has_mod_update_samples(),
    reason="old_mod.bundle AND new_original.bundle ARE REQUIRED"
)
class TestUpdateCommand:
    def test_update_basic(
        self,
        old_mod_bundle_paths: list[Path],
        new_original_bundle_paths: list[Path],
        tmp_path: Path,
    ):
        """测试基本的 update 功能"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # 构建多文件参数
        old_args = [str(p) for p in old_mod_bundle_paths]
        target_args = ["--target"] + [str(p) for p in new_original_bundle_paths]

        args = UpdateTap().parse_args(
            old_args + target_args + [
                "--output-dir", str(output_dir),
                "--no-crc",
                "--compression", "none",
                "--save-all",
            ]
        )

        logger = setup_cli_logger()
        handle_update(args, logger)

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) == len(new_original_bundle_paths)

        for output_file in output_files:
            bundle = Bundle.load(output_file)
            assert not bundle.is_empty(), f"Failed to load output bundle: {output_file}"

    def test_update_with_asset_types(
        self,
        old_mod_bundle_paths: list[Path],
        new_original_bundle_paths: list[Path],
        tmp_path: Path,
    ):
        """测试指定资源类型的 update"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # 构建多文件参数
        old_args = [str(p) for p in old_mod_bundle_paths]
        target_args = ["--target"] + [str(p) for p in new_original_bundle_paths]

        args = UpdateTap().parse_args(
            old_args + target_args + [
                "--output-dir", str(output_dir),
                "--asset-types", "Texture2D", "TextAsset",
                "--no-crc",
                "--compression", "none",
                "--save-all",
            ]
        )

        logger = setup_cli_logger()
        handle_update(args, logger)

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) == len(new_original_bundle_paths)

    def test_update_output_content(
        self,
        old_mod_bundle_paths: list[Path],
        new_original_bundle_paths: list[Path],
        tmp_path: Path,
    ):
        """测试 update 后的输出内容可以被加载"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # 构建多文件参数
        old_args = [str(p) for p in old_mod_bundle_paths]
        target_args = ["--target"] + [str(p) for p in new_original_bundle_paths]

        args = UpdateTap().parse_args(
            old_args + target_args + [
                "--output-dir", str(output_dir),
                "--no-crc",
                "--compression", "none",
                "--save-all",
            ]
        )

        logger = setup_cli_logger()
        handle_update(args, logger)

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) == len(new_original_bundle_paths)

        for output_file in output_files:
            bundle = Bundle.load(output_file)
            assert not bundle.is_empty(), f"Failed to load output bundle: {output_file}"

    def test_update_metadata_consistency(
        self,
        old_mod_bundle_paths: list[Path],
        new_original_bundle_paths: list[Path],
        tmp_path: Path,
    ):
        """测试 update 后元数据保持一致"""
        # 使用第一个 bundle 检查元数据
        new_original_bundle = Bundle.load(new_original_bundle_paths[0])
        original_platform, original_version = new_original_bundle.platform_info

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # 构建多文件参数
        old_args = [str(p) for p in old_mod_bundle_paths]
        target_args = ["--target"] + [str(p) for p in new_original_bundle_paths]

        args = UpdateTap().parse_args(
            old_args + target_args + [
                "--output-dir", str(output_dir),
                "--no-crc",
                "--compression", "none",
                "--save-all",
            ]
        )

        logger = setup_cli_logger()
        handle_update(args, logger)

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) == len(new_original_bundle_paths)

        for output_file in output_files:
            bundle = Bundle.load(output_file)
            assert not bundle.is_empty(), f"Failed to load output bundle: {output_file}"
            updated_platform, updated_version = bundle.platform_info
            assert updated_platform == original_platform
            assert updated_version == original_version

    def test_update_with_resource_dir(
        self,
        old_mod_bundle_paths: list[Path],
        new_original_bundle_paths: list[Path],
        tmp_path: Path,
    ):
        """测试使用 --resource-dir 自动搜索目标 bundle"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # 构建参数：不指定 --target，使用 --resource-dir 自动搜索
        old_args = [str(p) for p in old_mod_bundle_paths]
        resource_dir = new_original_bundle_paths[0].parent

        args = UpdateTap().parse_args(
            old_args + [
                "--resource-dir", str(resource_dir),
                "--output-dir", str(output_dir),
                "--no-crc",
                "--compression", "none",
                "--save-all",
            ]
        )

        logger = setup_cli_logger()
        handle_update(args, logger)

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) == len(new_original_bundle_paths)

        for output_file in output_files:
            bundle = Bundle.load(output_file)
            assert not bundle.is_empty(), f"Failed to load output bundle: {output_file}"