# naming.py

import csv
import re
from pathlib import Path
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
_RE_DATE = re.compile(r'(\d{4}-\d{2}-\d{2})')
_RE_MX = re.compile(r'[-_](?:mxdependency|mxload|mxprolog)')

# core 后缀 → 搜索前缀 映射（用于 core 匹配初筛，缩小 iterdir 范围）
_CORE_SUFFIX_PREFIX: dict[str, str] = {
    '_spr': 'assets-_mx-spinecharacters-',
    '_home': 'assets-_mx-spinelobbies-',
    '_home_gl': 'assets-_mx-spinelobbies-',
}
_DEFAULT_SEARCH_PREFIX = 'assets-_mx-characters-'

# 常见 mod 类型文件名前缀
COMMON_MOD_PREFIXES: list[str] = [
    'assets-_mx-spinelobbies-',
    'assets-_mx-spinecharacters-',
    'assets-_mx-characters-',
    'assets-_mx-npcs-',
    'assets-_mx-spinebackground-',
    'prologdepengroup-assets-_mx-characters-',
    'prologdepengroup-assets-_mx-spinecharacters-'
]


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
    # 1. 提取 CRC（从右向左切片）
    crc = ""
    stem = filename.rsplit('.', 1)[0]
    crc_idx = stem.rfind('_')
    if crc_idx != -1:
        candidate_crc = stem[crc_idx + 1:]
        if candidate_crc.isdigit():
            crc = candidate_crc

    # 2. 定位 Date 中轴
    match_date = _RE_DATE.search(filename)
    if not match_date:
        # 无日期情况（如 .skel / .png 散件素材）
        core_part = stem
        for p in PRELOAD_PREFIX:
            if core_part.startswith(p):
                core_part = core_part[len(p):]
                break
        for p in FIXED_PREFIX:
            if core_part.startswith(p):
                core_part = core_part[len(p):]
                break
        core = core_part.strip('-_')
        category = None
        if '-' in core:
            category, core = core.split('-', 1)
        return ParsedFilename(category=category, core=core, res_type=None, date="", crc=crc, prefix="")

    date = match_date.group(1)
    date_start = match_date.start()
    date_end = date_start + 10  # YYYY-MM-DD 固定长 10

    before_date = filename[:date_start]
    after_date = filename[date_end:]

    # 3. 基于“中轴两翼”判定 res_type 与 prefix
    res_type = None
    prefix = before_date

    # 3.1 检查左邻居：JP 格式 (res_type 在 date 之前，如 -textures-2024-...)
    left_token = before_date.rstrip('-_').rsplit('-', 1)[-1].lower()
    if left_token in RESOURCE_TYPES_TEXT:
        res_type = left_token
        before_clean = before_date.removesuffix('-')
        prefix = before_clean.removesuffix(f"-{res_type}") + '-'

    # 3.2 检查右邻居：Modern 格式 (res_type 在 date 之后，如 _002_)
    elif len(after_date) >= 5 and after_date[0] == '_' and after_date[4] == '_':
        right_token = after_date[1:4]
        if right_token.isdigit():
            res_type = right_token

    # 4. 提取 Core 与 Category
    # 截掉 mx 依赖标记
    match_mx = _RE_MX.search(prefix)
    if match_mx:
        core_part = prefix[:match_mx.start()]
    else:
        core_part = prefix.rstrip('-_')

    # 双重前缀需分两轮独立剥离
    # 第一轮：剥离 Preload 前缀 (prologdepengroup-)
    for p in PRELOAD_PREFIX:
        if core_part.startswith(p):
            core_part = core_part[len(p):]
            break
    # 第二轮：剥离 Fixed 前缀 (assets-_mx-)
    for p in FIXED_PREFIX:
        if core_part.startswith(p):
            core_part = core_part[len(p):]
            break

    core = core_part.strip('-_')
    category = None
    if '-' in core:
        category, core = core.split('-', 1)

    return ParsedFilename(
        category=category,
        core=core,
        res_type=res_type,
        date=date,
        crc=crc,
        prefix=prefix
    )


# -------- 角色ID映射 --------

# core 值中需要剥离的已知后缀
_CORE_SUFFIXES = (
    "_spr",
    "_home",
    "_home_gl",
    "_original"
    )


class CharacterInternalIDMap:
    """角色ID映射表，从 CSV 加载 core → 角色名称的映射"""

    # 可用的名称字段
    NAME_FIELDS = ["full_name", "name_cn", "name_jp", "name_tw", "name_en", "name_kr"]

    def __init__(self):
        self._map: dict[str, dict[str, str]] = {}

    def load(self, csv_path: Path) -> bool:
        """从 CSV 文件加载映射表，返回是否成功"""
        self._map.clear()
        if not csv_path.exists():
            return False
        try:
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    file_id = row.get("file_id", "").strip()
                    if not file_id:
                        continue
                    self._map[file_id.lower()] = {
                        "full_name": row.get("full_name", ""),
                        "name_cn": row.get("name_cn", ""),
                        "name_jp": row.get("name_jp", ""),
                        "name_tw": row.get("name_tw", ""),
                        "name_en": row.get("name_en", ""),
                        "name_kr": row.get("name_kr", ""),
                    }
            return True
        except Exception as e:
            print(f"Failed to load BACII: {e}")
            return False

    @property
    def loaded(self) -> bool:
        """映射表是否已加载"""
        return bool(self._map)

    def lookup(self, core: str, field: str = "full_name") -> str | None:
        """根据 core 值查找角色名称

        Args:
            core: 解析后的 core 值（如 ch0808_spr）
            field: 映射字段名（如 full_name, name_cn 等）
        
        Returns:
            角色名称，未找到则返回 None
        """
        core_lower = core.lower()
        # 先尝试原值匹配
        entry = self._map.get(core_lower)
        # 未找到则尝试剥离后缀
        if entry is None:
            for suffix in _CORE_SUFFIXES:
                if core_lower.endswith(suffix):
                    entry = self._map.get(core_lower.removesuffix(suffix))
                    break
        if entry is None:
            return None
        name = entry.get(field, "")
        return name if name else None
