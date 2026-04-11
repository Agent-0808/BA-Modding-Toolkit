import pytest
import shutil
from pathlib import Path

from ba_modding_toolkit.bundle import Bundle
from ba_modding_toolkit.cli.taps import SplitTap, MergeTap
from ba_modding_toolkit.cli.handlers import handle_split, handle_merge
from conftest import has_legacy_format_samples


@pytest.mark.skipif(
    not has_legacy_format_samples(),
    reason="Legacy bundle AND modern bundles ARE REQUIRED"
)
class TestSplitCommand:
    def test_split_with_resource_dir(
        self,
        legacy_bundle_path: Path,
        modern_dir_path: Path,
        tmp_path: Path,
    ):
        """测试使用 --resource-dir 参数的 split 功能"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        args = SplitTap().parse_args([
            str(legacy_bundle_path),
            "--resource-dir", str(modern_dir_path),
            "--output-dir", str(output_dir),
            "--no-crc",
            "--compression", "none",
        ])

        handle_split(args)

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) > 0, "No output files generated"
        b1 = Bundle.load(output_files[0])
        assert not b1.is_empty()

    def test_split_with_modern_files(
        self,
        legacy_bundle_path: Path,
        modern_bundles_path: list[Path],
        tmp_path: Path,
    ):
        """测试使用 --modern-files 参数的 split 功能"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        args = SplitTap().parse_args([
            str(legacy_bundle_path),
            "--modern-files", *[str(p) for p in modern_bundles_path],
            "--output-dir", str(output_dir),
            "--no-crc",
            "--compression", "none",
        ])

        handle_split(args)

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) > 0, "No output files generated"

    def test_split_output_content(
        self,
        legacy_bundle_path: Path,
        modern_dir_path: Path,
        tmp_path: Path,
    ):
        """测试 split 后的输出内容可以被加载"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        args = SplitTap().parse_args([
            str(legacy_bundle_path),
            "--resource-dir", str(modern_dir_path),
            "--output-dir", str(output_dir),
            "--no-crc",
            "--compression", "none",
        ])

        handle_split(args)

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) > 0

        for output_file in output_files:
            bundle = Bundle.load(output_file)
            assert not bundle.is_empty(), f"Failed to load output bundle: {output_file}"


@pytest.mark.skipif(
    not has_legacy_format_samples(),
    reason="Legacy bundle AND modern bundles ARE REQUIRED"
)
class TestMergeCommand:
    def test_merge_with_resource_dir(
        self,
        legacy_bundle_path: Path,
        modern_dir_path: Path,
        tmp_path: Path,
    ):
        """测试使用 --resource-dir 参数的 merge 功能"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        args = MergeTap().parse_args([
            str(legacy_bundle_path),
            "--resource-dir", str(modern_dir_path),
            "--output-dir", str(output_dir),
            "--no-crc",
            "--compression", "none",
        ])

        handle_merge(args)

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) > 0, "No output files generated"

    def test_merge_with_modern_files(
        self,
        legacy_bundle_path: Path,
        modern_bundles_path: list[Path],
        tmp_path: Path,
    ):
        """测试使用 --modern-files 参数的 merge 功能"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        args = MergeTap().parse_args([
            str(legacy_bundle_path),
            "--modern-files", *[str(p) for p in modern_bundles_path],
            "--output-dir", str(output_dir),
            "--no-crc",
            "--compression", "none",
        ])

        handle_merge(args)

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) > 0, "No output files generated"

    def test_merge_output_content(
        self,
        legacy_bundle_path: Path,
        modern_dir_path: Path,
        tmp_path: Path,
    ):
        """测试 merge 后的输出内容可以被加载"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        args = MergeTap().parse_args([
            str(legacy_bundle_path),
            "--resource-dir", str(modern_dir_path),
            "--output-dir", str(output_dir),
            "--no-crc",
            "--compression", "none",
        ])

        handle_merge(args)

        output_files = list(output_dir.glob("*.bundle"))
        assert len(output_files) > 0

        for output_file in output_files:
            bundle = Bundle.load(output_file)
            assert not bundle.is_empty(), f"Failed to load output bundle: {output_file}"