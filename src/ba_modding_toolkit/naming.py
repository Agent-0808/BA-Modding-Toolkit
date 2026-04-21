# naming.py

import re
from .models import ParsedFilename

# -------- 文件名解析常量 --------

REMOVE_SUFFIX = [
    r"[-_]mxdependency",  # 匹配 -mxdependency 或 _mxdependency
    r"[-_]mxload",        # 匹配 -mxload 或 _mxload
    r"-\d{4}-\d{2}-\d{2}" # 匹配日期格式 (如 -2024-11-18)，作为最后的保底
]

FIXED_PREFIX = [
    "assets-_mx-",
]

# 日服版额外的资源类型后缀
RESOURCE_TYPES = {
    'textures', 'assets', 'textassets', 'materials',
    "animationclip", "audio", "meshes", "prefabs", "timelines"
}


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
    match_crc = re.search(r'_(\d+)\.[^.]+$', filename)
    if match_crc:
        crc = match_crc.group(1)

    # 提取 Date
    date = ""
    prefix_end_index = 0
    match_date = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
    if match_date:
        date = match_date.group(1)
        prefix_end_index = match_date.start()

    # 提取 Type
    res_type = None
    # 匹配 -mxdependency-xxx 或 _mxload-xxx
    match_type = re.search(r'[-_](?:mxdependency|mxload)-([a-zA-Z0-9]+)', filename)
    if match_type:
        extracted = match_type.group(1)
        # 如果提取出的 type 是年份，说明实际上没有 type，而是直接接了日期
        if re.match(r'^\d{4}$', extracted):
            res_type = None
            # 国际服 Modern 版：res_type 在日期之后（如 -2024-11-18_002_assets）
            match_modern = re.search(r'\d{4}-\d{2}-\d{2}_([0-9]{3})_', filename)
            if match_modern:
                res_type = match_modern.group(1)
        else:
            res_type = extracted

    # 找到最早的 _mxdependency 或 _mxload 位置
    mx_match = re.search(r'[-_](?:mxdependency|mxload)', filename)
    if mx_match:
        # Core 是这之前的部分
        core_part = filename[:mx_match.start()]
    else:
        # 如果没找到，尝试用日期作为分隔
        date_match = re.search(r'-\d{4}-\d{2}-\d{2}', filename)
        if date_match:
            core_part = filename[:date_match.start()]
        else:
            # 最后的保底：去除扩展名
            core_part = filename.rsplit('.', 1)[0]

    # 去除固定前缀
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
        before_date = filename[:prefix_end_index].removesuffix('-')
        parts = before_date.split('-')
        last_part = parts[-1] if parts else ''
        
        if last_part.lower() in RESOURCE_TYPES:
            prefix = before_date.removesuffix(f'-{last_part}') + '-'
        else:
            prefix = filename[:prefix_end_index]

    return ParsedFilename(
        category=category,
        core=core,
        res_type=res_type,
        date=date,
        crc=crc,
        prefix=prefix
    )
