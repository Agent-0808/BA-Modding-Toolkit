# searching.py

from pathlib import Path

from .i18n import t
from .utils import no_log
from .naming import parse_filename, get_category_prefix
from .models import LogFunc, AssetKey, AssetType, BundleFileInfo, ProgressCallback
from .bundle import Bundle


def collect_candidates_by_prefix(
    source_paths: list[Path],
    search_dirs: list[Path],
    log: LogFunc = no_log,
) -> tuple[list[Path], str]:
    """
    通过文件名前缀(prefix)匹配，在搜索目录中收集候选目标文件。

    Args:
        source_paths: 源文件路径列表
        search_dirs: 搜索目录列表
        log: 日志记录函数

    Returns:
        tuple[list[Path], str]: (候选文件路径列表, 错误消息)
        - 成功时: (candidates, "")
        - 失败时: ([], 错误消息)
    """
    prefix = parse_filename(str(source_paths[0].name)).prefix

    if not prefix:
        msg = t("message.search.filename_parse_failed")
        log(f'  > {t("common.fail")}: {msg}')
        return [], msg

    log(f"  > {t('log.search.file_prefix', prefix=prefix)}")
    extension_backup = '.backup'

    candidates = [
        file for dir in search_dirs
        if dir.exists() and dir.is_dir()
        for file in dir.iterdir()
        if file.is_file() and file.name.startswith(prefix) and file.suffix != extension_backup
    ]

    if not candidates:
        msg = t("message.search.no_matching_files_in_dir")
        log(f'  > {t("common.fail")}: {msg}')
        return [], msg

    log(f"  > {t('log.search.found_candidates', count=len(candidates))}")
    return candidates, ""


def collect_candidates_by_core(
    source_paths: list[Path],
    search_dirs: list[Path],
    log: LogFunc = no_log,
) -> tuple[list[Path], str]:
    """
    通过文件名核心部分(core)匹配，在搜索目录中收集候选目标文件。
    先通过字符串包含匹配进行初筛，再通过 parse_filename 确认 core 相同。

    Args:
        source_paths: 源文件路径列表
        search_dirs: 搜索目录列表
        log: 日志记录函数

    Returns:
        tuple[list[Path], str]: (候选文件路径列表, 错误消息)
    """
    parsed = parse_filename(str(source_paths[0].name))
    core = parsed.core

    if not core:
        msg = t("message.search.filename_parse_failed")
        log(f'  > {t("common.fail")}: {msg}')
        return [], msg

    log(f"  > {t('log.search.file_core', core=core)}")
    extension_backup = '.backup'

    # 字符串包含匹配，粗筛
    core_lower = core.lower()
    search_prefix = get_category_prefix(core_lower)
    rough = [
        file for dir in search_dirs
        if dir.exists() and dir.is_dir()
        for file in dir.iterdir()
        if file.is_file() and file.name.startswith(search_prefix)
        and core_lower in file.name.lower() and file.suffix != extension_backup
    ]

    # 第二轮：parse_filename 确认 core 相同（大小写不敏感）
    candidates = [
        file for file in rough
        if parse_filename(file.name).core.lower() == core_lower
    ]

    if not candidates:
        msg = t("message.search.no_matching_files_in_dir")
        log(f'  > {t("common.fail")}: {msg}')
        return [], msg

    log(f"  > {t('log.search.found_candidates', count=len(candidates))}")
    return candidates, ""


def _asset_match(
    source_paths: list[Path],
    candidates: list[Path],
    log: LogFunc = no_log,
) -> tuple[list[Path], str]:
    """
    对候选文件进行指纹比对，筛选出与源文件组匹配的目标文件。

    Returns:
        tuple[list[Path], str]: (匹配的文件路径列表, 状态消息)
    """
    comparable_types = {AssetType.Texture2D, AssetType.TextAsset, AssetType.Mesh}
    strategy = 'name_type'

    source_assets: set[AssetKey] = set()
    for src_path in source_paths:
        src_bundle = Bundle.load(src_path, log)
        if not src_bundle:
            continue
        source_assets |= src_bundle.get_asset_keys(strategy, comparable_types)

    if not source_assets:
        msg = t("message.search.no_comparable_assets")
        log(f'  > {t("common.fail")}: {msg}')
        return [], msg

    log(f"  > {t('log.search.source_mod_asset_count', count=len(source_assets))}")

    matched_paths: list[Path] = []
    for candidate_path in candidates:
        log(f"  - {t('log.search.checking_candidate', name=candidate_path.name)}")

        candidate_bundle = Bundle.load(candidate_path, log)
        if not candidate_bundle:
            continue

        candidate_keys = candidate_bundle.get_asset_keys(strategy, comparable_types)
        if candidate_keys & source_assets:
            matched_paths.append(candidate_path)
            msg = t("message.search.new_file_confirmed", name=candidate_path.name)
            log(f"  ✅ {msg}")

    if not matched_paths:
        msg = t("message.search.no_matching_asset_found")
        log(f'  > {t("common.fail")}: {msg}')
        return [], msg

    msg = t("message.search.found_multiple_matches", count=len(matched_paths))
    log(f"  > {msg}")
    return matched_paths, msg


def find_target_bundles(
    source_paths: list[Path],
    game_resource_dir: Path | list[Path],
    log: LogFunc = no_log,
) -> tuple[list[Path], str]:
    """
    根据源文件组，在游戏资源目录中智能查找对应的目标文件组（通过前缀匹配）。

    Returns:
        tuple[list[Path], str]: (找到的目标路径列表, 状态消息)
    """
    if not source_paths:
        return [], t("message.search.check_file_exists", path="[]")

    log(t("log.search.searching_for_file_group", count=len(source_paths)))

    search_dirs = [game_resource_dir] if isinstance(game_resource_dir, Path) else game_resource_dir

    candidates, err_msg = collect_candidates_by_prefix(source_paths, search_dirs, log)
    if not candidates:
        return [], err_msg

    return _asset_match(source_paths, candidates, log)


SEARCH_DIR_SUFFIXES = [
    "",
    "BlueArchive_Data/StreamingAssets/PUB/Resource/GameData/Windows",
    "BlueArchive_Data/StreamingAssets/PUB/Resource/Preload/Windows",
    "GameData/Windows",
    "Preload/Windows",
    "GameData/Android",
    "Preload/Android",
]

def get_search_dirs(base_dir: Path) -> list[Path]:
    """
    获取游戏资源搜索目录列表。
    """
    
    ret = [
        base_dir / suffix
        for suffix in SEARCH_DIR_SUFFIXES
        if (base_dir / suffix).is_dir()
    ]
    return ret


def scan_bundle_files(
    base_dir: Path,
    log: LogFunc = no_log,
    progress_callback: ProgressCallback | None = None,
) -> list[BundleFileInfo]:
    """
    扫描搜索目录下的所有 bundle 文件，收集文件信息。

    Args:
        base_dir: 游戏资源根目录
        log: 日志记录函数
        progress_callback: 进度回调函数，接收 (已完成数, 总数, 文件名)

    Returns:
        BundleFileInfo 列表
    """
    search_dirs = get_search_dirs(base_dir)
    if not search_dirs:
        log(t("message.search.no_matching_files_in_dir"))
        return []

    all_bundles: list[Path] = []
    seen: set[Path] = set()

    for directory in search_dirs:
        for bundle_path in sorted(directory.iterdir()):
            if not bundle_path.is_file() or bundle_path.suffix != '.bundle':
                continue
            if bundle_path in seen:
                continue
            seen.add(bundle_path)
            all_bundles.append(bundle_path)

    total = len(all_bundles)
    results: list[BundleFileInfo] = []

    for i, bundle_path in enumerate(all_bundles):
        trailing = Bundle.get_trailing_bytes(bundle_path)
        content = None
        if trailing is not None and trailing > 0:
            content = Bundle.get_trailing_content(bundle_path, trailing)

        crc_expected = parse_filename(bundle_path.name).crc

        results.append(BundleFileInfo(
            path=bundle_path,
            file_size=bundle_path.stat().st_size,
            trailing_bytes=trailing,
            trailing_content=content,
            crc_expected=crc_expected,
        ))

        if progress_callback:
            progress_callback(i + 1, total, bundle_path.name)

    return results
