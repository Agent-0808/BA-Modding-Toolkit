# utils/__init__.py
"""通用工具包 — 各子模块公开名的统一出口，保持 `from .utils import X` 兼容"""

from .common import (
    CREATE_NO_WINDOW,
    LogFunc,
    ProgressCallback,
    is_safe_file_name,
    is_safe_relative_name,
    no_log,
    parse_hex_bytes,
    run_batch,
    throttle_progress,
    timing,
)
from .crc import (
    apply_crc_fix,
    check_crc_match,
    compute_crc32,
    manipulate_file_crc,
)
from .image import (
    DEFAULT_TEXTURE_MSE_THRESHOLD,
    bleed_image,
    compare_texture,
    is_same_texture,
    mse_to_similarity,
    texture_mse,
)
from .paths import BARegion, EXE_DIR, PACKAGE_DIR, get_BA_path
from .about import get_environment_info, get_version_info

__all__ = [
    "CREATE_NO_WINDOW",
    "LogFunc",
    "is_safe_file_name",
    "is_safe_relative_name",
    "no_log",
    "parse_hex_bytes",
    "ProgressCallback",
    "run_batch",
    "throttle_progress",
    "timing",
    "apply_crc_fix",
    "check_crc_match",
    "compute_crc32",
    "manipulate_file_crc",
    "bleed_image",
    "texture_mse",
    "is_same_texture",
    "compare_texture",
    "mse_to_similarity",
    "DEFAULT_TEXTURE_MSE_THRESHOLD",
    "BARegion",
    "EXE_DIR",
    "PACKAGE_DIR",
    "get_BA_path",
    "get_environment_info",
    "get_version_info",
]
