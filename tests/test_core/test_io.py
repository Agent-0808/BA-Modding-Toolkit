"""
Bundle文件I/O测试

测试以下功能:
- Bundle.load: 加载bundle文件
- Bundle.compress: 压缩方式 (lzma, lz4, none)
- Bundle.save: 保存bundle文件
- CRC修正与extra_bytes
"""

import pytest
from pathlib import Path

from ba_modding_toolkit.bundle import Bundle
from ba_modding_toolkit.models import SaveOptions
from ba_modding_toolkit.utils import CRCUtils
from conftest import has_sample_bundle


@pytest.mark.skipif(
    not has_sample_bundle(),
    reason="sample.bundle IS REQUIRED"
)
class TestLoadBundle:
    def test_load_bundle_basic(self, sample_bundle_path: Path):
        bundle = Bundle.load(sample_bundle_path)
        assert not bundle.is_empty()

    def test_load_bundle_read_assets(self, sample_bundle_path: Path):
        bundle = Bundle.load(sample_bundle_path)
        assert not bundle.is_empty()
        
        asset_count = 0
        for obj in bundle.env.objects:
            data = obj.read()
            if hasattr(data, 'm_Name'):
                asset_count += 1
        assert asset_count > 0

    def test_load_bundle_nonexistent(self, tmp_path: Path):
        nonexistent = tmp_path / "nonexistent.bundle"
        bundle = Bundle.load(nonexistent)
        # UnityPy.load 对于不存在的文件会创建一个空的 Environment
        assert bundle.is_empty()


@pytest.mark.skipif(
    not has_sample_bundle(),
    reason="sample.bundle IS REQUIRED"
)
class TestSaveBundle:
    def test_save_without_crc(
        self, sample_bundle_path: Path, tmp_path: Path
    ):
        bundle = Bundle.load(sample_bundle_path)
        assert not bundle.is_empty()
        
        output_path = tmp_path / "output_no_crc.bundle"
        save_options = SaveOptions(
            perform_crc=False,
            compression="none",
        )
        
        success, msg = bundle.save(output_path, save_options)
        assert success is True, msg
        
        actual_crc = CRCUtils.compute_crc32(output_path)
        assert actual_crc != 99999999

    def test_crc_fix_with_specific_target(
        self, sample_bundle_path: Path, tmp_path: Path
    ):
        bundle = Bundle.load(sample_bundle_path)
        assert not bundle.is_empty()
        
        target_crc = 0xDEADBEEF
        output_name = f"test_2024-01-01_{target_crc}.bundle"
        output_path = tmp_path / output_name
        
        save_options = SaveOptions(
            perform_crc=True,
            compression="lzma",
        )
        
        success, msg = bundle.save(output_path, save_options)
        assert success is True, msg
        
        actual_crc = CRCUtils.compute_crc32(output_path)
        assert actual_crc == target_crc


@pytest.mark.skipif(
    not has_sample_bundle(),
    reason="sample.bundle IS REQUIRED"
)
class TestExtraBytes:
    def test_save_with_extra_bytes(
        self, sample_bundle_path: Path, tmp_path: Path
    ):
        bundle = Bundle.load(sample_bundle_path)
        assert not bundle.is_empty()
        
        target_crc = 87654321
        output_name = f"test_2024-01-01_{target_crc}.bundle"
        output_path = tmp_path / output_name
        
        extra_bytes = b"\x00\x01\x02\x03\x04\x05\x06\x07"
        save_options = SaveOptions(
            perform_crc=True,
            extra_bytes=extra_bytes,
            compression="none",
        )
        
        success, msg = bundle.save(output_path, save_options)
        assert success is True, msg
        
        output_data = output_path.read_bytes()
        actual_crc = CRCUtils.compute_crc32(output_path)
        assert actual_crc == target_crc
        assert output_data[-len(extra_bytes) - 4 : -4] == extra_bytes

    def test_save_with_extra_bytes_and_compression(
        self, sample_bundle_path: Path, tmp_path: Path
    ):
        bundle = Bundle.load(sample_bundle_path)
        assert not bundle.is_empty()
        
        target_crc = 11223344
        output_name = f"test_2077-08-08_{target_crc}.bundle"
        output_path = tmp_path / output_name
        
        extra_bytes = b"EXTRA_DATA"
        save_options = SaveOptions(
            perform_crc=True,
            extra_bytes=extra_bytes,
            compression="lzma",
        )
        
        success, msg = bundle.save(output_path, save_options)
        assert success is True, msg
        
        output_data = output_path.read_bytes()
        assert output_data[-len(extra_bytes) - 4 : -4] == extra_bytes


@pytest.mark.skipif(
    not has_sample_bundle(),
    reason="sample.bundle IS REQUIRED"
)
class TestCompressBundle:
    @pytest.mark.parametrize("compression", ["lzma", "lz4", "none"])
    def test_compress_bundle(self, sample_bundle_path: Path, compression: str):
        bundle = Bundle.load(sample_bundle_path)
        assert not bundle.is_empty()
        
        data = bundle.compress(compression)
        assert isinstance(data, bytes)
        assert len(data) > 0

    @pytest.mark.parametrize("compression", ["lzma", "lz4", "none"])
    def test_full_roundtrip(
        self, sample_bundle_path: Path, tmp_path: Path, compression: str
    ):
        bundle = Bundle.load(sample_bundle_path)
        assert not bundle.is_empty()
        
        target_crc = 99887766
        output_name = f"test_2024-01-01_{target_crc}.bundle"
        output_path = tmp_path / output_name
        
        save_options = SaveOptions(
            perform_crc=True,
            compression=compression,
        )
        
        success, msg = bundle.save(output_path, save_options)
        assert success is True, msg
        
        reloaded_bundle = Bundle.load(output_path)
        assert not reloaded_bundle.is_empty()
        
        actual_crc = CRCUtils.compute_crc32(output_path)
        assert actual_crc == target_crc

    @pytest.mark.parametrize("compression", ["lzma", "lz4", "none"])
    def test_full_roundtrip_with_extra_bytes(
        self, sample_bundle_path: Path, tmp_path: Path, compression: str
    ):
        bundle = Bundle.load(sample_bundle_path)
        assert not bundle.is_empty()
        
        target_crc = 13579246
        output_name = f"test_2024-01-01_{target_crc}.bundle"
        output_path = tmp_path / output_name
        
        extra_bytes = b"\x11\x22\x33\x44"
        save_options = SaveOptions(
            perform_crc=True,
            extra_bytes=extra_bytes,
            compression=compression,
        )
        
        success, msg = bundle.save(output_path, save_options)
        assert success is True, msg
        
        reloaded_bundle = Bundle.load(output_path)
        assert not reloaded_bundle.is_empty()
        
        output_data = output_path.read_bytes()
        actual_crc = CRCUtils.compute_crc32(output_data)
        assert actual_crc == target_crc
        assert output_data[-len(extra_bytes) - 4 : -4] == extra_bytes

    def test_compression_lzma_smaller_than_none(
        self, sample_bundle_path: Path, tmp_path: Path
    ):
        bundle = Bundle.load(sample_bundle_path)
        assert not bundle.is_empty()
        
        lzma_data = bundle.compress("lzma")
        none_data = bundle.compress("none")
        
        assert len(lzma_data) < len(none_data)
