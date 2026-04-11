import pytest
from pathlib import Path

from ba_modding_toolkit.cli.taps import ExtractTap
from ba_modding_toolkit.cli.handlers import handle_extract
from conftest import has_sample_bundle, has_legacy_format_samples


@pytest.mark.skipif(
    not has_sample_bundle(),
    reason="Sample bundle file IS REQUIRED"
)
class TestExtractCommand:
    def test_extract_basic(
        self,
        sample_bundle_path: Path,
        tmp_path: Path,
    ):
        """测试基本的 extract 功能"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        args = ExtractTap().parse_args([
            str(sample_bundle_path),
            "--output-dir", str(output_dir),
        ])

        handle_extract(args)

        extracted_files = list(output_dir.rglob("*"))
        assert len(extracted_files) > 0, "No files extracted"

    def test_extract_with_subdir(
        self,
        sample_bundle_path: Path,
        tmp_path: Path,
    ):
        """测试指定子目录的 extract"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        args = ExtractTap().parse_args([
            str(sample_bundle_path),
            "--output-dir", str(output_dir),
            "--subdir", "test_extract",
        ])

        handle_extract(args)

        subdir = output_dir / "test_extract"
        assert subdir.exists(), "Subdirectory not created"

        extracted_files = list(subdir.rglob("*"))
        assert len(extracted_files) > 0


@pytest.mark.skipif(
    not has_legacy_format_samples(),
    reason="Modern bundles in legacy_format are REQUIRED"
)
class TestExtractMultipleBundles:
    def test_extract_multiple_bundles(
        self,
        modern_dir_path: Path,
        tmp_path: Path,
    ):
        """测试提取多个 bundle"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # 获取 modern 目录下的所有 bundle 文件
        modern_bundles = sorted(modern_dir_path.glob("*.bundle"))
        assert len(modern_bundles) > 0, "No bundle files found in modern directory"

        args = ExtractTap().parse_args([
            *[str(b) for b in modern_bundles],
            "--output-dir", str(output_dir),
        ])

        handle_extract(args)

        extracted_files = list(output_dir.rglob("*"))
        assert len(extracted_files) > 0, "No files extracted from multiple bundles"
