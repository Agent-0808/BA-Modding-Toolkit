# log.report.py
"""Mod 报告生成核心逻辑"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .bundle import analyze_trailing, analyze_naming
from .i18n import t
from .models import BundleFileInfo, LogFunc, ProgressCallback
from .naming import CharacterInternalIDMap
from .searching import list_bundle_files
from .core import render_spine_preview_from_bundle
from .utils import no_log


# 分类映射
CATEGORY_MAP: dict[str, str] = {
    "spinecharacters": "Character Art",
    "spinelobbies": "Memory Lobby",
    "characters": "Model",
    "npcs": "Model(NPC)",
    "spinebackground": "Other Spine",
}

# 分类输出顺序
OUTPUT_ORDER = ["spinecharacters", "spinelobbies", "characters", "npcs", "spinebackground", "other"]

# 渲染分类（仅 Spine 资源）
RENDER_CATEGORIES = {"spinecharacters", "spinelobbies", "spinebackground"}


@dataclass
class ModEntry:
    """单个 mod 条目（聚合后）"""
    prefix: str
    core: str | None
    category: str | None
    char_name: str | None
    res_types: list[str] = field(default_factory=list)
    files: list[Path] = field(default_factory=list)
    render_success: bool = True


@dataclass
class ModReport:
    """完整报告数据"""
    generated_time: str
    game_dir: str
    total_count: int
    category_counts: dict[str, int]
    categories: dict[str, list[ModEntry]]


def generate_mod_report(
    game_dir: Path,
    output_path: Path,
    char_map: CharacterInternalIDMap | None = None,
    char_name_field: str = "full_name",
    enable_render: bool = False,
    viewer_path: Path | None = None,
    log: LogFunc = no_log,
    progress_callback: ProgressCallback | None = None,
) -> tuple[bool, str]:
    """
    生成 Mod 报告。

    Args:
        game_dir: 游戏资源目录
        output_path: 报告输出路径（.md 文件）
        char_map: 角色名称映射表
        char_name_field: 角色名称字段
        enable_render: 是否生成 Spine 预览图
        viewer_path: SpineViewerCLI 路径
        log: 日志函数
        progress_callback: 进度回调函数

    Returns:
        tuple[bool, str]: (是否成功, 状态消息)
    """
    log(f"--- {t('log.report.scan_start')} ---")

    # 1. 扫描 bundle 文件
    items = list_bundle_files(game_dir)
    if not items:
        msg = t("log.report.no_bundle_found")
        log(f"⚠️ {msg}")
        return False, msg

    log(f"{t('log.report.bundle_count', count=len(items))}")

    # 2. 分析尾部字节
    log(f"--- {t('log.report.analyze_trailing')} ---")
    total = len(items)
    for i, item in enumerate(items):
        analyze_trailing(item)
        analyze_naming(item)
        if progress_callback:
            progress_callback(i + 1, total, item.path.name)

    # 3. 筛选 mod 文件
    mod_items = [item for item in items if item.trailing_bytes and item.trailing_bytes > 0]
    if not mod_items:
        msg = t("log.report.no_mod_found")
        log(f"⚠️ {msg}")
        return False, msg

    log(f"{t('log.report.mod_count', count=len(mod_items))}")

    # 4. 按 prefix 聚合
    entries = _aggregate_mods(mod_items, char_map, char_name_field)

    # 5. 按 category 分类
    categories: dict[str, list[ModEntry]] = {}
    for entry in entries:
        cat_key = entry.category or "other"
        if cat_key not in categories:
            categories[cat_key] = []
        categories[cat_key].append(entry)

    # 6. 统计数量
    category_counts = {cat: len(entries) for cat, entries in categories.items()}

    # 7. 可选：渲染 Spine 预览图
    if enable_render and viewer_path:
        log(f"--- {t('log.report.render_preview')} ---")
        output_dir = output_path.parent / output_path.stem
        output_dir.mkdir(parents=True, exist_ok=True)

        render_count = 0
        for cat, cat_entries in categories.items():
            if cat not in RENDER_CATEGORIES:
                continue
            for entry in cat_entries:
                if not entry.files:
                    continue
                
                success, _ = render_spine_preview_from_bundle(
                    bundle_path=entry.files,
                    output_dir=output_dir,
                    viewer_path=viewer_path,
                    output_filename=entry.prefix,
                    log=log,
                )
                if success:
                    render_count += 1
                else:
                    entry.render_success = False

        log(f"{t('log.report.render_count', count=render_count)}")

    # 8. 生成报告
    report = ModReport(
        generated_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        game_dir=str(game_dir),
        total_count=len(entries),
        category_counts=category_counts,
        categories=categories,
    )

    _write_report(report, output_path, enable_render)
    log(f"✓ {t('log.report.saved', path=output_path)}")

    return True, t("log.report.success", count=len(entries))


def _aggregate_mods(
    items: list[BundleFileInfo],
    char_map: CharacterInternalIDMap | None,
    char_name_field: str,
) -> list[ModEntry]:
    """按 prefix 聚合 mod 文件"""
    grouped: dict[str, ModEntry] = {}

    for item in items:
        parsed = item.parsed_name
        if not parsed:
            continue

        prefix = parsed.prefix
        core = parsed.core
        category = parsed.category
        res_type = parsed.res_type or "base"

        if prefix not in grouped:
            # 查询角色名
            char_name = None
            if char_map and core:
                char_name = char_map.lookup(core, char_name_field)

            grouped[prefix] = ModEntry(
                prefix=prefix,
                core=core,
                category=category,
                char_name=char_name,
            )

        # 添加版本和文件
        if res_type and res_type not in grouped[prefix].res_types:
            grouped[prefix].res_types.append(res_type)
        grouped[prefix].files.append(item.path)

    return list(grouped.values())


def _write_report(report: ModReport, output_path: Path, enable_render: bool) -> None:
    """写入 Markdown 报告"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 报告内容使用英文（CLI 不需要本地化）
    lines = [
        f"# Mod Report",
        f"Generated: `{report.generated_time}`",
        f"Scan Directory: `{report.game_dir}`",
        f"Total Mods: {report.total_count}",
    ]

    # 添加分类统计列表
    for cat in OUTPUT_ORDER:
        if cat in report.category_counts:
            cat_name = CATEGORY_MAP.get(cat, "Other")
            lines.append(f"- {cat_name}: {report.category_counts[cat]}")

    # 其他不在 OUTPUT_ORDER 中的分类
    for cat, count in report.category_counts.items():
        if cat not in OUTPUT_ORDER:
            cat_name = CATEGORY_MAP.get(cat, "Other")
            lines.append(f"- {cat_name}: {count}")

    lines.append("")  # 空行分隔

    # 按 OUTPUT_ORDER 顺序输出详细列表
    for cat in OUTPUT_ORDER:
        if cat not in report.categories:
            continue
        entries = report.categories[cat]
        cat_name = CATEGORY_MAP.get(cat, "Other")
        lines.append(f"### {cat_name}")

        for entry in entries:
            line = _format_entry(entry, output_path, enable_render)
            lines.append(line)
        lines.append("")

    # 处理不在输出顺序中的其他分类
    for cat, entries in report.categories.items():
        if cat in OUTPUT_ORDER:
            continue
        cat_name = CATEGORY_MAP.get(cat, "Other")
        lines.append(f"### {cat_name}")

        for entry in entries:
            line = _format_entry(entry, output_path, enable_render)
            lines.append(line)
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def _format_entry(entry: ModEntry, output_path: Path, enable_render: bool) -> str:
    """格式化单个条目"""
    # 角色名 - core - 版本号
    parts = []
    if entry.char_name:
        parts.append(entry.char_name)
    if entry.core:
        parts.append(entry.core)
    if entry.res_types:
        parts.append(", ".join(entry.res_types))

    line = "- " + " - ".join(parts)

    # 渲染失败标记
    if not entry.render_success:
        line += " ⚠️"

    # 图片引用
    if enable_render and entry.category in RENDER_CATEGORIES and entry.render_success:
        img_dir = output_path.stem
        img_name = entry.prefix.replace("/", "_").replace("\\", "_")
        line += f"\n  ![]({img_dir}/{img_name}.png)"

    return line