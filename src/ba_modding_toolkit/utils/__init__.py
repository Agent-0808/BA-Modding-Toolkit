# utils/__init__.py
"""通用工具包 — 各子模块公开名的统一出口，保持 `from .utils import X` 兼容"""

from .common import (
    CREATE_NO_WINDOW,
    LogFunc,
    ProgressCallback,
    no_log,
    parse_hex_bytes,
    throttle_progress,
    timing,
)
from .crc import (
    apply_crc_fix,
    check_crc_match,
    compute_crc32,
    manipulate_file_crc,
)
from .image import bleed_image
from .paths import BARegion, EXE_DIR, PACKAGE_DIR, get_BA_path
from .about import get_environment_info, get_version_info

__all__ = [
    "CREATE_NO_WINDOW",
    "LogFunc",
    "no_log",
    "parse_hex_bytes",
    "ProgressCallback",
    "throttle_progress",
    "timing",
    "apply_crc_fix",
    "check_crc_match",
    "compute_crc32",
    "manipulate_file_crc",
    "bleed_image",
    "BARegion",
    "EXE_DIR",
    "PACKAGE_DIR",
    "get_BA_path",
    "get_environment_info",
    "get_version_info",
]
