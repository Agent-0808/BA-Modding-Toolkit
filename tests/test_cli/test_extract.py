from pathlib import Path
from typing import TYPE_CHECKING

from ba_modding_toolkit.cli.taps import ExtractTap
from ba_modding_toolkit.cli.handlers import handle_extract

if TYPE_CHECKING:
    from conftest import SampleCase, UpdateCase

# 案例数据缺失时 conftest 参数化为空参数集，测试自动跳过
class TestExtractCommand:
    def test_extract_basic(
        self,
        sample_case: "SampleCase",
        tmp_path: Path,
    ):
        """测试基本的 extract 功能"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        args = ExtractTap().parse_args([
            str(sample_case.bundle_paths[0]),
            "--output-dir", str(output_dir),
        ])

        handle_extract(args)

        extracted_files = list(output_dir.rglob("*"))
        assert len(extracted_files) > 0, "No files extracted"

    def test_extract_with_subdir(
        self,
        sample_case: "SampleCase",
        tmp_path: Path,
    ):
        """测试指定子目录的 extract"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        args = ExtractTap().parse_args([
            str(sample_case.bundle_paths[0]),
            "--output-dir", str(output_dir),
            "--subdir", "test_extract",
        ])

        handle_extract(args)

        subdir = output_dir / "test_extract"
        assert subdir.exists(), "Subdirectory not created"

        extracted_files = list(subdir.rglob("*"))
        assert len(extracted_files) > 0


class TestExtractMultipleBundles:
    def test_extract_multiple_bundles(
        self,
        update_case: "UpdateCase",
        tmp_path: Path,
    ):
        """测试提取多个 bundle"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        assert len(update_case.new_paths) > 0, "No bundle files found in update case"

        args = ExtractTap().parse_args([
            *[str(b) for b in update_case.new_paths],
            "--output-dir", str(output_dir),
        ])

        handle_extract(args)

        extracted_files = list(output_dir.rglob("*"))
        assert len(extracted_files) > 0, "No files extracted from multiple bundles"
