# core/__init__.py
"""核心处理流程包。

拆分自原 core.py：
- packing: 资源打包（替换）
- extraction: 资源提取
- mod_update: Mod 更新（单文件 / 批量）
- preview: Spine 预览图渲染
- report: Mod 报告生成
- mod_install: Mod 安装（plan / execute）
"""

from .packing import process_asset_packing
from .extraction import EXTRACTABLE_ASSET_TYPES, extract_assets_from_bundle, process_asset_extraction
from .mod_update import process_mod_update, process_batch_mod_update
from .preview import (
    RENDER_CATEGORIES,
    RenderTask,
    render_all_spine_previews,
    render_spine_previews_batch,
    render_spine_preview_from_bundle,
)
from .report import ReportFormat, generate_mod_report

__all__ = [
    "EXTRACTABLE_ASSET_TYPES",
    "RENDER_CATEGORIES",
    "RenderTask",
    "ReportFormat",
    "extract_assets_from_bundle",
    "generate_mod_report",
    "process_asset_extraction",
    "process_asset_packing",
    "process_batch_mod_update",
    "process_mod_update",
    "render_all_spine_previews",
    "render_spine_previews_batch",
    "render_spine_preview_from_bundle",
]
