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
from typing import TYPE_CHECKING
import shutil

from ba_modding_toolkit.bundle import Bundle
from ba_modding_toolkit.models import SaveOptions
from ba_modding_toolkit.utils import compute_crc32

if TYPE_CHECKING:
    from conftest import SampleCase

# 案例数据缺失时 conftest 参数化为空参数集，测试自动跳过
class TestLoadBundle:
    def test_load_bundle_basic(self, sample_case: "SampleCase"):
        bundle = Bundle.load(sample_case.bundle_paths[0])
        assert not bundle.is_empty()

    def test_load_bundle_read_assets(self, sample_case: "SampleCase"):
        bundle = Bundle.load(sample_case.bundle_paths[0])
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
        # 不存在的文件应该返回 None
        assert bundle is None


class TestTrailingBytes:
    """尾部字节检测的蜕变测试：对 tmp_path 中的真实素材副本做追加/还原"""

    def test_baseline_non_negative(self, sample_case: "SampleCase"):
        """合法 bundle 的检测值非负，且与实际可读回的尾部内容长度一致"""
        source = sample_case.bundle_paths[0]
        baseline = Bundle.get_trailing_bytes(source)
        assert baseline is not None
        assert baseline >= 0
        # 检测到的尾部字节数 == 实际读回内容的长度（两 API 自洽）
        content = Bundle.get_trailing_content(source, baseline)
        assert len(content) == baseline

    def test_append_and_truncate(self, sample_case: "SampleCase", tmp_path: Path):
        """追加 N 字节 → 检测值 +N 且内容可读回；截断还原 → 回到基线（可逆性）"""

        source = sample_case.bundle_paths[0]
        assert Bundle.load(source) is not None, "素材应可加载"
        work = tmp_path / source.name
        shutil.copy2(source, work)
        baseline = Bundle.get_trailing_bytes(work)
        assert baseline is not None

        extra = b"BA-MODDING-TOOLKIT"
        with open(work, "ab") as f:
            f.write(extra)
        assert Bundle.get_trailing_bytes(work) == baseline + len(extra)
        assert Bundle.get_trailing_content(work, len(extra)) == extra  # 读回 == 追加内容

        # max_bytes 截断：读取尾部最后 8 字节（尾部内容取自文件末尾）
        assert Bundle.get_trailing_content(work, len(extra), max_bytes=8) == extra[-8:]

        # 截断还原：文件字节恢复原样 → 检测值回到基线
        work.write_bytes(work.read_bytes()[:-len(extra)])
        assert Bundle.get_trailing_bytes(work) == baseline


class TestSaveBundle:
    def test_save_without_crc(
        self, sample_case: "SampleCase", tmp_path: Path
    ):
        bundle = Bundle.load(sample_case.bundle_paths[0])
        assert not bundle.is_empty()
        
        output_path = tmp_path / "output_no_crc.bundle"
        save_options = SaveOptions(
            perform_crc=False,
            compression="none",
        )
        
        success, msg = bundle.save(output_path, save_options)
        assert success is True, msg
        
        actual_crc = compute_crc32(output_path)
        assert actual_crc != 99999999

    def test_crc_fix_with_specific_target(
        self, sample_case: "SampleCase", tmp_path: Path
    ):
        bundle = Bundle.load(sample_case.bundle_paths[0])
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
        
        actual_crc = compute_crc32(output_path)
        assert actual_crc == target_crc


class TestExtraBytes:
    def test_save_with_extra_bytes(
        self, sample_case: "SampleCase", tmp_path: Path
    ):
        bundle = Bundle.load(sample_case.bundle_paths[0])
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
        actual_crc = compute_crc32(output_path)
        assert actual_crc == target_crc
        assert output_data[-len(extra_bytes) - 4 : -4] == extra_bytes

    def test_save_with_extra_bytes_and_compression(
        self, sample_case: "SampleCase", tmp_path: Path
    ):
        bundle = Bundle.load(sample_case.bundle_paths[0])
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


class TestCompressBundle:
    @pytest.mark.parametrize("compression", ["lzma", "lz4", "none"])
    def test_compress_bundle(self, sample_case: "SampleCase", compression: str):
        bundle = Bundle.load(sample_case.bundle_paths[0])
        assert not bundle.is_empty()
        
        data = bundle.compress(compression)
        assert isinstance(data, bytes)
        assert len(data) > 0

    @pytest.mark.parametrize("compression", ["lzma", "lz4", "none"])
    def test_full_roundtrip(
        self, sample_case: "SampleCase", tmp_path: Path, compression: str
    ):
        bundle = Bundle.load(sample_case.bundle_paths[0])
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
        
        actual_crc = compute_crc32(output_path)
        assert actual_crc == target_crc

    @pytest.mark.parametrize("compression", ["lzma", "lz4", "none"])
    def test_full_roundtrip_with_extra_bytes(
        self, sample_case: "SampleCase", tmp_path: Path, compression: str
    ):
        bundle = Bundle.load(sample_case.bundle_paths[0])
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
        actual_crc = compute_crc32(output_data)
        assert actual_crc == target_crc
        assert output_data[-len(extra_bytes) - 4 : -4] == extra_bytes

    def test_compression_lzma_smaller_than_none(
        self, sample_case: "SampleCase", tmp_path: Path
    ):
        bundle = Bundle.load(sample_case.bundle_paths[0])
        assert not bundle.is_empty()
        
        lzma_data = bundle.compress("lzma")
        none_data = bundle.compress("none")
        
        assert len(lzma_data) < len(none_data)
