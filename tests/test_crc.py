"""
CRC修正功能的测试用例

测试以下函数:
- CRCUtils.compute_crc32(data: bytes) -> int
- CRCUtils.check_crc_match(source, target) -> tuple[bool, int, int]
- CRCUtils.apply_crc_fix(modified_data: bytes, target_crc: int) -> bytes | None
- CRCUtils.manipulate_file_crc(modified_path: Path, target_crc: int, extra_bytes: bytes | None = None) -> bool
"""

import pytest
from pathlib import Path
import shutil
from typing import TYPE_CHECKING

from ba_modding_toolkit.utils import CRCUtils

if TYPE_CHECKING:
    from conftest import SampleCase


class TestComputeCrc32:
    def test_basic_crc32(self):
        assert CRCUtils.compute_crc32(b"hello world") == 222957957
        assert CRCUtils.compute_crc32(b"") == 0
        assert CRCUtils.compute_crc32(b"test") == 3632233996
        assert CRCUtils.compute_crc32(b"0808") == 206773752
    
    def test_compute_crc32_2_methods(self, tmp_path: Path):
        data = b"8080 0800 8800 0888 8080 0800 8088 0000 8080 0800 8800 0008 8080 0800 8800 8888 8080 0800 8088 8008 8080 0800 8088 0000 8080 0800 8088 8808 8080 0800 8088 0088"
        file = tmp_path / "test.bin"
        file.write_bytes(data)
        assert CRCUtils.compute_crc32(file) == CRCUtils.compute_crc32(data)


class TestCheckCrcMatch:
    def test_same_data(self):
        data = b"test data for crc"
        match, crc1, crc2 = CRCUtils.check_crc_match(data, data)
        assert match is True
        assert crc1 == crc2

    def test_different_data(self):
        data1 = b"data one"
        data2 = b"data two"
        match, crc1, crc2 = CRCUtils.check_crc_match(data1, data2)
        assert match is False
        assert crc1 != crc2

    def test_with_files(self, tmp_path: Path):
        file1 = tmp_path / "file1.bin"
        file2 = tmp_path / "file2.bin"
        file1.write_bytes(b"same content")
        file2.write_bytes(b"same content")
        
        match, crc1, crc2 = CRCUtils.check_crc_match(file1, file2)
        assert match is True
        assert crc1 == crc2


class TestApplyCrcFix:
    def test_basic_crc_fix(self):
        original_data = b"Hello, World!"
        original_crc = CRCUtils.compute_crc32(original_data)
        modified_data = b"Hello, Modified Data!"
        
        corrected_data = CRCUtils.apply_crc_fix(modified_data, original_crc)
        
        assert corrected_data is not None
        assert len(corrected_data) == len(modified_data) + 4
        assert CRCUtils.compute_crc32(corrected_data) == original_crc

    def test_crc_fix_with_binary_data(self):
        original_data = bytes(range(256))
        original_crc = CRCUtils.compute_crc32(original_data)
        modified_data = bytes(range(255, -1, -1))
        
        corrected_data = CRCUtils.apply_crc_fix(modified_data, original_crc)
        
        assert corrected_data is not None
        assert CRCUtils.compute_crc32(corrected_data) == original_crc

    def test_crc_fix_with_large_data(self):
        original_crc = CRCUtils.compute_crc32(b"A" * 10000)
        modified_data = b"B" * 5000
        
        corrected_data = CRCUtils.apply_crc_fix(modified_data, original_crc)
        
        assert corrected_data is not None
        assert CRCUtils.compute_crc32(corrected_data) == original_crc

    def test_crc_fix_with_specific_target_crc(self):
        modified_data = b"Some random data"
        target_crc = 0x12345678
        
        corrected_data = CRCUtils.apply_crc_fix(modified_data, target_crc)
        
        assert corrected_data is not None
        assert CRCUtils.compute_crc32(corrected_data) == target_crc

    def test_crc_fix_with_zero_target_crc(self):
        modified_data = b"Test data for zero CRC"
        target_crc = 0x00000000
        
        corrected_data = CRCUtils.apply_crc_fix(modified_data, target_crc)
        
        assert corrected_data is not None
        assert CRCUtils.compute_crc32(corrected_data) == target_crc

    def test_crc_fix_with_max_target_crc(self):
        modified_data = b"Test data for max CRC"
        target_crc = 0xFFFFFFFF
        
        corrected_data = CRCUtils.apply_crc_fix(modified_data, target_crc)
        
        assert corrected_data is not None
        assert CRCUtils.compute_crc32(corrected_data) == target_crc

    def test_crc_fix_preserves_original_data(self):
        modified_data = b"Original content that should be preserved"
        target_crc = 0xDEADBEEF
        
        corrected_data = CRCUtils.apply_crc_fix(modified_data, target_crc)
        
        assert corrected_data is not None
        assert corrected_data[:len(modified_data)] == modified_data

    def test_apply_crc_fix_simple(self):
        data = b"test data for crc modification"
        target_crc = 7355608
        
        fixed_data = CRCUtils.apply_crc_fix(data, target_crc)
        
        assert fixed_data is not None
        assert CRCUtils.compute_crc32(fixed_data) == target_crc

    def test_apply_crc_fix_zero_target(self):
        data = b"some data"
        fixed_data = CRCUtils.apply_crc_fix(data, 0)
        
        assert fixed_data is not None
        assert CRCUtils.compute_crc32(fixed_data) == 0


class TestManipulateFileCrc:
    def test_basic_file_crc_manipulation(self, tmp_path: Path):
        test_file = tmp_path / "test_file.bin"
        original_crc = CRCUtils.compute_crc32(b"File content for testing")
        modified_data = b"Modified file content here"
        test_file.write_bytes(modified_data)
        
        result = CRCUtils.manipulate_file_crc(test_file, original_crc)
        
        assert result is True
        corrected_data = test_file.read_bytes()
        assert len(corrected_data) == len(modified_data) + 4
        assert CRCUtils.compute_crc32(corrected_data) == original_crc

    def test_file_crc_manipulation_with_extra_bytes(self, tmp_path: Path):
        test_file = tmp_path / "test_file.bin"
        original_crc = CRCUtils.compute_crc32(b"Original data")
        modified_data = b"Modified data"
        test_file.write_bytes(modified_data)
        
        extra_bytes = b"\x00\x01\x02\x03"
        result = CRCUtils.manipulate_file_crc(test_file, original_crc, extra_bytes)
        
        assert result is True
        corrected_data = test_file.read_bytes()
        # [modified_bytes, extra_bytes, crc(4B)]
        assert len(corrected_data) == len(modified_data) + len(extra_bytes) + 4
        assert corrected_data[:len(modified_data)] == modified_data
        assert corrected_data[len(modified_data):-4] == extra_bytes
        assert CRCUtils.compute_crc32(corrected_data) == original_crc

    def test_file_crc_manipulation_failure(self, tmp_path: Path):
        non_existent_file = tmp_path / "non_existent.bin"
        
        with pytest.raises(FileNotFoundError):
            CRCUtils.manipulate_file_crc(non_existent_file, 0x12345678)

    def test_file_crc_manipulation_empty_file(self, tmp_path: Path):
        test_file = tmp_path / "test_file.bin"
        target_crc = 0xCAFEBABE
        test_file.write_bytes(b"")
        
        result = CRCUtils.manipulate_file_crc(test_file, target_crc)
        
        assert result is True
        corrected_data = test_file.read_bytes()
        assert len(corrected_data) == 4
        assert CRCUtils.compute_crc32(corrected_data) == target_crc

    def test_file_crc_manipulation_preserves_content(self, tmp_path: Path):
        test_file = tmp_path / "test_file.bin"
        modified_data = b"Content that must be preserved exactly"
        target_crc = 0x11223344
        test_file.write_bytes(modified_data)
        
        result = CRCUtils.manipulate_file_crc(test_file, target_crc)
        
        assert result is True
        corrected_data = test_file.read_bytes()
        assert corrected_data[:len(modified_data)] == modified_data

    def test_file_crc_manipulation_with_binary_content(self, tmp_path: Path):
        test_file = tmp_path / "test_file.bin"
        modified_data = bytes([i % 256 for i in range(1000)])
        target_crc = 0x08080808
        test_file.write_bytes(modified_data)
        
        result = CRCUtils.manipulate_file_crc(test_file, target_crc)
        
        assert result is True
        assert CRCUtils.compute_crc32(test_file.read_bytes()) == target_crc

    def test_manipulate_file_crc_simple(self, tmp_path: Path):
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"original content")
        target_crc = 80808080
        
        result = CRCUtils.manipulate_file_crc(test_file, target_crc)
        
        assert result is True
        assert CRCUtils.compute_crc32(test_file) == target_crc


class TestCrcFixIntegration:
    def test_full_crc_fix_workflow(self, tmp_path: Path):
        source_file = tmp_path / "source.bin"
        modified_file = tmp_path / "modified.bin"
        
        original_data = b"This is the original file content"
        source_file.write_bytes(original_data)
        original_crc = CRCUtils.compute_crc32(original_data)
        
        modified_data = b"This is the modified file content with some changes"
        modified_file.write_bytes(modified_data)
        
        result = CRCUtils.manipulate_file_crc(modified_file, original_crc)
        assert result is True
        
        corrected_data = modified_file.read_bytes()
        assert CRCUtils.compute_crc32(corrected_data) == original_crc
        
        direct_corrected = CRCUtils.apply_crc_fix(modified_data, original_crc)
        assert corrected_data == direct_corrected

    def test_crc_fix_round_trip(self):
        data = b"Test data for round trip"
        target_crc = 0xAABBCCDD
        
        corrected1 = CRCUtils.apply_crc_fix(data, target_crc)
        assert corrected1 is not None
        assert CRCUtils.compute_crc32(corrected1) == target_crc
        
        corrected2 = CRCUtils.apply_crc_fix(corrected1, target_crc)
        assert corrected2 is not None
        assert CRCUtils.compute_crc32(corrected2) == target_crc
        
        assert corrected1 != corrected2
        assert len(corrected2) == len(corrected1) + 4


class TestCrcWithBundle:
    def test_compute_crc32_from_bundle(self, sample_case: "SampleCase"):
        crc = CRCUtils.compute_crc32(sample_case.bundle_paths[0])

        assert isinstance(crc, int)
        assert 0 <= crc <= 0xFFFFFFFF

    def test_check_crc_match_same_bundle(self, sample_case: "SampleCase", tmp_path: Path):
        copy_file = tmp_path / "copy.bundle"
        shutil.copy(sample_case.bundle_paths[0], copy_file)

        match, crc1, crc2 = CRCUtils.check_crc_match(sample_case.bundle_paths[0], copy_file)

        assert match is True
        assert crc1 == crc2

    def test_check_crc_match_modified_bundle(self, sample_case: "SampleCase", tmp_path: Path):
        modified_file = tmp_path / "modified.bundle"
        data = sample_case.bundle_paths[0].read_bytes()
        modified_data = data[:-1] + bytes([data[-1] ^ 0xFF])
        modified_file.write_bytes(modified_data)

        match, crc1, crc2 = CRCUtils.check_crc_match(sample_case.bundle_paths[0], modified_file)

        assert match is False
        assert crc1 != crc2

    def test_manipulate_bundle_crc(self, sample_case: "SampleCase", tmp_path: Path):
        test_file = tmp_path / "test.bundle"
        shutil.copy(sample_case.bundle_paths[0], test_file)
        
        target_crc = 0x12345678
        
        result = CRCUtils.manipulate_file_crc(test_file, target_crc)
        
        assert result is True
        assert CRCUtils.compute_crc32(test_file) == target_crc

    def test_bundle_crc_fix_preserves_content(self, sample_case: "SampleCase", tmp_path: Path):
        test_file = tmp_path / "test.bundle"
        original_data = sample_case.bundle_paths[0].read_bytes()
        modified_data = original_data[:-4] + b"TEST"
        test_file.write_bytes(modified_data)
        
        target_crc = CRCUtils.compute_crc32(original_data)
        result = CRCUtils.manipulate_file_crc(test_file, target_crc)
        
        assert result is True
        corrected_data = test_file.read_bytes()
        assert corrected_data[:len(modified_data)] == modified_data
        assert CRCUtils.compute_crc32(corrected_data) == target_crc
