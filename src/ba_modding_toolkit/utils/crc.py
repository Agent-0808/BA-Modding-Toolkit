# utils/crc.py
"""CRC32 计算与修正工具（原 CRCUtils 类打散为模块级函数）。

Prototype by [kalina](https://github.com/kalinaowo)
"""

import binascii
from pathlib import Path

# --- 原类常量，转为模块私有常量 ---
_POLY_NORMAL = 0x104C11DB7
_POLY_DEGREE = 32
_GF2_INVERSE_X32 = 0xCBF1ACDA
_BIT_REVERSE_TABLE = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))


def compute_crc32(src: Path | str | bytes) -> int:
    """
    计算数据的标准CRC32 (IEEE)值。
    """
    if isinstance(src, bytes):
        return binascii.crc32(src) & 0xFFFFFFFF
    return _compute_crc32_file(src)


def _compute_crc32_file(path: str | Path) -> int:
    """分块计算文件 CRC32，避免大文件内存溢出"""
    crc = 0
    with open(path, "rb") as f:
        while chunk := f.read(8192):  # 8KB 分块
            crc = binascii.crc32(chunk, crc)
    return crc & 0xFFFFFFFF


def check_crc_match(source_1: Path | str | bytes, source_2: Path | str | bytes) -> tuple[bool, int, int]:
    """
    检测两个文件或字节数据的CRC值是否匹配。
    返回 (是否匹配, crc_1, crc_2)。
    """
    crc_1 = compute_crc32(source_1)
    crc_2 = compute_crc32(source_2)

    return crc_1 == crc_2, crc_1, crc_2


def apply_crc_fix(modified_data: bytes, target_crc: int) -> bytes | None:
    """
    计算修正CRC后的数据，使其达到指定的目标CRC值。
    如果修正成功，返回修正后的完整字节数据；如果失败，返回None。
    """
    # 计算新数据加上4个空字节的CRC，为修正值留出空间
    base_crc = binascii.crc32(modified_data)
    crc_with_zeros = binascii.crc32(b'\x00\x00\x00\x00', base_crc) & 0xFFFFFFFF
    k = _reverse_bits_32(target_crc ^ crc_with_zeros)

    correction_value = _gf2_multiply_mod(k, _GF2_INVERSE_X32)
    correction_bytes = _reverse_bytes_internal_bits(correction_value)
    final_data = modified_data + correction_bytes

    final_crc = compute_crc32(final_data)
    is_crc_match = (final_crc == target_crc)
    return final_data if is_crc_match else None


def manipulate_file_crc(modified_path: str | Path, target_crc: int, extra_bytes: bytes | None = None) -> bool:
    """
    修正modified_path文件的CRC，使其达到指定的目标CRC值
    这个函数会直接修改文件内容，而不是输出到指定目录
    extra_bytes: 可选的 N 字节数据，将在CRC计算前附加到modified_data后
    """
    with open(str(modified_path), "rb") as f:
        modified_data = f.read()

    if extra_bytes:
        modified_data = modified_data + extra_bytes

    corrected_data = apply_crc_fix(modified_data, target_crc)

    if corrected_data:
        with open(modified_path, "wb") as f:
            f.write(corrected_data)
        return True

    return False


# --- 内部使用的私有辅助函数 ---

def _reverse_bits_32(val_u32: int) -> int:
    """快速翻转 32 位整数的所有比特位"""
    b = val_u32.to_bytes(4, 'big')
    rev_b = bytes(_BIT_REVERSE_TABLE[x] for x in b[::-1])
    return int.from_bytes(rev_b, 'big')


def _reverse_bytes_internal_bits(val_u32: int) -> int:
    """将整数转为字节，并反转每个字节内部的比特位"""
    b = val_u32.to_bytes(4, 'big')
    return bytes(_BIT_REVERSE_TABLE[x] for x in b)


def _gf2_multiply_mod(a, b):
    result = 0
    while b != 0:
        if b & 1:
            result ^= a
        b >>= 1
        a <<= 1
        if a >> _POLY_DEGREE:
            a ^= _POLY_NORMAL
    return result
