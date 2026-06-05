# naming.py

import re
from .models import ParsedFilename

# -------- 文件名解析常量 --------

PRELOAD_PREFIX = [
    "prologgroup-",
    "prologdepengroup-"
]

FIXED_PREFIX = [
    "assets-_mx-",
]

# 日服版额外的资源类型后缀
RESOURCE_TYPES_TEXT = {
    'textures', 'textassets', 'meshes', 'materials',
    'assets', 'animationclips', 'audio', 'prefabs', 'timelines'
}
RESOURCE_TYPES_NUM = {
    '000', '001', '002', '003', '004', '005', '006', '007', '008', '009',
    '010', '011', '012', '013', '014', '015', '016', '017', '018', '019',
}

# -------- 预编译正则（避免 per-call 编译开销）--------
_RE_CRC = re.compile(r'_(\d+)\.[^.]+$')
_RE_DATE = re.compile(r'(\d{4}-\d{2}-\d{2})')
_RE_TYPE = re.compile(r'[-_](?:mxdependency|mxload|mxprolog)-([a-zA-Z0-9]+)')
_RE_MODERN = re.compile(r'\d{4}-\d{2}-\d{2}_([0-9]{3})_')
_RE_YEAR = re.compile(r'^\d{4}$')

# core 后缀 → 搜索前缀 映射（用于 core 匹配初筛，缩小 iterdir 范围）
_CORE_SUFFIX_PREFIX: dict[str, str] = {
    '_spr': 'assets-_mx-spinecharacters-',
    '_home': 'assets-_mx-spinelobbies-',
}
_DEFAULT_SEARCH_PREFIX = 'assets-_mx-characters-'


def get_category_prefix(core: str) -> str:
    """根据 core 后缀返回对应的搜索前缀"""
    core_lower = core.lower()
    for suffix, prefix in _CORE_SUFFIX_PREFIX.items():
        if core_lower.endswith(suffix):
            return prefix
    return _DEFAULT_SEARCH_PREFIX


def parse_filename(filename: str) -> ParsedFilename:
    """
    解析文件名，提取各个组成部分。

    Args:
        filename: 文件名字符串

    Returns:
        ParsedFilename: 包含所有解析字段的命名元组
    """
    # 提取 CRC32
    crc = ""
    match_crc = _RE_CRC.search(filename)
    if match_crc:
        crc = match_crc.group(1)

    # 提取 Date（同时记录日期起始位置）
    date = ""
    date_start = 0
    match_date = _RE_DATE.search(filename)
    if match_date:
        date = match_date.group(1)
        date_start = match_date.start()

    # 提取 res_type 和 mx 位置（一次 _RE_TYPE 搜索同时获取）
    res_type = None
    mx_start = 0
    match_type = _RE_TYPE.search(filename)
    if match_type:
        mx_start = match_type.start()
        extracted = match_type.group(1)
        # 如果提取出的是年份，说明没有 type，而是直接接了日期
        if _RE_YEAR.match(extracted):
            res_type = None
            # 国际服 Modern 版：res_type 在日期之后（如 -2024-11-18_002_assets）
            match_modern = _RE_MODERN.search(filename)
            if match_modern:
                res_type = match_modern.group(1)
        else:
            res_type = extracted

    # 提取 core_part（利用 _RE_TYPE 已找到的 mx 位置，无需再次搜索）
    if mx_start > 0:
        core_part = filename[:mx_start]
    elif date_start > 1:
        # 无 mx 标记时，以日期前的 `-` 为界
        core_part = filename[:date_start - 1]
    else:
        core_part = filename.rsplit('.', 1)[0]

    # 去除前缀
    for preload_prefix in PRELOAD_PREFIX:
        if core_part.startswith(preload_prefix):
            core_part = core_part[len(preload_prefix):]
            break
    for fixed_prefix in FIXED_PREFIX:
        if core_part.startswith(fixed_prefix):
            core_part = core_part[len(fixed_prefix):]
            break

    core = core_part.strip('-_')

    # 提取 Category
    category = None
    if core:
        parts = core.split('-', 1)
        if len(parts) > 1:
            category = parts[0]
            core = parts[1]

    # 计算 prefix（用于搜索新版文件）
    prefix = ""
    if date:
        if res_type and res_type.lower() in RESOURCE_TYPES_TEXT:
            # JP 格式：文本类型 res_type 在日期之前，需从 prefix 中剥离
            before_date = filename[:date_start].removesuffix('-')
            prefix = before_date.removesuffix(f'-{res_type}') + '-'
        else:
            prefix = filename[:date_start]

    return ParsedFilename(
        category=category,
        core=core,
        res_type=res_type,
        date=date,
        crc=crc,
        prefix=prefix
    )
