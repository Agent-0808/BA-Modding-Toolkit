from pathlib import Path
from typing import TYPE_CHECKING

from ba_modding_toolkit.bundle import Bundle
from ba_modding_toolkit.cli.taps import UpdateTap
from ba_modding_toolkit.cli.handlers import handle_update, setup_cli_logger

if TYPE_CHECKING:
    from conftest import UpdateCase

# 案例数据缺失时 conftest 参数化为空参数集，测试自动跳过
class TestUpdateCommand:
    def test_update_basic(
        self,
        update_case: "UpdateCase",
        tmp_path: Path,
    ):
        """测试基本的 update 功能"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # 构建多文件参数
        old_args = [str(p) for p in update_case.old_paths]
        target_args = ["--target"] + [str(p) for p in update_case.new_paths]

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
        assert len(output_files) == len(update_case.new_paths)

        for output_file in output_files:
            bundle = Bundle.load(output_file)
            assert not bundle.is_empty(), f"Failed to load output bundle: {output_file}"

    def test_update_with_asset_types(
        self,
        update_case: "UpdateCase",
        tmp_path: Path,
    ):
        """测试指定资源类型的 update"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # 构建多文件参数
        old_args = [str(p) for p in update_case.old_paths]
        target_args = ["--target"] + [str(p) for p in update_case.new_paths]

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
        assert len(output_files) == len(update_case.new_paths)

    def test_update_output_content(
        self,
        update_case: "UpdateCase",
        tmp_path: Path,
    ):
        """测试 update 后的输出内容可以被加载"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # 构建多文件参数
        old_args = [str(p) for p in update_case.old_paths]
        target_args = ["--target"] + [str(p) for p in update_case.new_paths]

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
        assert len(output_files) == len(update_case.new_paths)

        for output_file in output_files:
            bundle = Bundle.load(output_file)
            assert not bundle.is_empty(), f"Failed to load output bundle: {output_file}"

    def test_update_metadata_consistency(
        self,
        update_case: "UpdateCase",
        tmp_path: Path,
    ):
        """测试 update 后元数据保持一致"""
        # 使用第一个 bundle 检查元数据
        new_original_bundle = Bundle.load(update_case.new_paths[0])
        original_platform, original_version = new_original_bundle.platform_info

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # 构建多文件参数
        old_args = [str(p) for p in update_case.old_paths]
        target_args = ["--target"] + [str(p) for p in update_case.new_paths]

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
        assert len(output_files) == len(update_case.new_paths)

        for output_file in output_files:
            bundle = Bundle.load(output_file)
            assert not bundle.is_empty(), f"Failed to load output bundle: {output_file}"
            updated_platform, updated_version = bundle.platform_info
            assert updated_platform == original_platform
            assert updated_version == original_version

    def test_update_with_resource_dir(
        self,
        update_case: "UpdateCase",
        tmp_path: Path,
    ):
        """测试使用 --resource-dir 自动搜索目标 bundle"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # 构建参数：不指定 --target，使用 --resource-dir 自动搜索
        old_args = [str(p) for p in update_case.old_paths]
        resource_dir = update_case.new_paths[0].parent

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
        assert len(output_files) == len(update_case.new_paths)

        for output_file in output_files:
            bundle = Bundle.load(output_file)
            assert not bundle.is_empty(), f"Failed to load output bundle: {output_file}"