import pytest
from pathlib import Path

from ba_modding_toolkit.cli.taps import CrcTap
from ba_modding_toolkit.cli.handlers import handle_crc
from conftest import has_sample_bundle


@pytest.mark.skipif(
    not has_sample_bundle(),
    reason="Sample bundle file IS REQUIRED"
)
class TestCrcCommand:
    def test_crc_check_only(
        self,
        sample_bundle_path: Path,
        tmp_path: Path,
    ):
        """测试 CRC 检查模式（不修改文件）"""
        args = CrcTap().parse_args([
            str(sample_bundle_path),
            "--check-only",
        ])

        handle_crc(args)

    def test_crc_with_original(
        self,
        sample_bundle_path: Path,
        tmp_path: Path,
    ):
        """测试指定原始文件的 CRC 修复"""
        modified_file = tmp_path / "modified.bundle"
        modified_file.write_bytes(sample_bundle_path.read_bytes())

        args = CrcTap().parse_args([
            str(modified_file),
            "--original", str(sample_bundle_path),
        ])

        handle_crc(args)

    def test_crc_no_backup(
        self,
        sample_bundle_path: Path,
        tmp_path: Path,
    ):
        """测试不创建备份的 CRC 修复"""
        modified_file = tmp_path / "modified.bundle"
        modified_file.write_bytes(sample_bundle_path.read_bytes())

        args = CrcTap().parse_args([
            str(modified_file),
            "--check-only",
            "--no-backup",
        ])

        handle_crc(args)
