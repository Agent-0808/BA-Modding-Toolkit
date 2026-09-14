import pytest
from pathlib import Path

from ba_modding_toolkit.cli.taps import CrcTap
from ba_modding_toolkit.cli.handlers import handle_crc
from ba_modding_toolkit.utils import CRCUtils
from conftest import has_sample_bundle


@pytest.mark.skipif(
    not has_sample_bundle(),
    reason="Sample bundle file IS REQUIRED"
)
class TestCrcCommand:
    def test_crc_check(
        self,
        sample_bundle_path: Path
    ):
        """测试 CRC 检查模式（单文件计算，不修改文件）"""
        args = CrcTap().parse_args([
            str(sample_bundle_path),
            "--check",
        ])

        handle_crc(args)

    def test_crc_compare_two_files(
        self,
        sample_bundle_path: Path,
        tmp_path: Path,
    ):
        """测试 CRC 检查模式（双文件对比）"""
        other_file = tmp_path / "other.bundle"
        other_file.write_bytes(sample_bundle_path.read_bytes())

        args = CrcTap().parse_args([
            str(sample_bundle_path),
            str(other_file),
            "--check",
        ])

        handle_crc(args)

    def test_crc_fix_with_target_crc(
        self,
        sample_bundle_path: Path,
        tmp_path: Path,
    ):
        """测试显式指定目标 CRC 的修复"""
        modified_file = tmp_path / "modified.bundle"
        modified_file.write_bytes(sample_bundle_path.read_bytes())

        args = CrcTap().parse_args([
            str(modified_file),
            "--target-crc", "0x00000000",
        ])

        handle_crc(args)

        with open(modified_file, "rb") as f:
            assert CRCUtils.compute_crc32(f.read()) == 0

    def test_crc_fix_from_filename(
        self,
        sample_bundle_path: Path,
        tmp_path: Path,
    ):
        """测试从文件名提取目标 CRC 的修复（默认创建备份）"""
        modified_file = tmp_path / "123456_assets_all_1234567890.bundle"
        modified_file.write_bytes(sample_bundle_path.read_bytes())

        args = CrcTap().parse_args([
            str(modified_file),
        ])

        handle_crc(args)

        with open(modified_file, "rb") as f:
            assert CRCUtils.compute_crc32(f.read()) == 1234567890
        assert modified_file.with_suffix(modified_file.suffix + '.backup').is_file()

    def test_crc_fix_no_backup(
        self,
        sample_bundle_path: Path,
        tmp_path: Path,
    ):
        """测试不创建备份的 CRC 修复"""
        modified_file = tmp_path / "123456_assets_all_1234567890.bundle"
        modified_file.write_bytes(sample_bundle_path.read_bytes())

        args = CrcTap().parse_args([
            str(modified_file),
            "--no-backup",
        ])

        handle_crc(args)

        with open(modified_file, "rb") as f:
            assert CRCUtils.compute_crc32(f.read()) == 1234567890
        assert not modified_file.with_suffix(modified_file.suffix + '.backup').exists()
