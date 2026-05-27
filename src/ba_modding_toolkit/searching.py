# searching.py

from pathlib import Path

from .i18n import t
from .utils import no_log
from .naming import parse_filename
from .models import LogFunc, AssetKey, AssetType
from .bundle import Bundle


def _collect_candidates_by_prefix(
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
        msg = t("message.search.date_pattern_not_found", filename=source_paths[0].name)
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


def _collect_candidates_by_core(
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
        msg = t("message.search.date_pattern_not_found", filename=source_paths[0].name)
        log(f'  > {t("common.fail")}: {msg}')
        return [], msg

    log(f"  > {t('log.search.file_core', core=core)}")
    extension_backup = '.backup'

    # 字符串包含匹配，粗筛
    rough = [
        file for dir in search_dirs
        if dir.exists() and dir.is_dir()
        for file in dir.iterdir()
        if file.is_file() and core in file.name and file.suffix != extension_backup
    ]

    # 第二轮：parse_filename 确认 core 相同
    candidates = [
        file for file in rough
        if parse_filename(file.name).core == core
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

    candidates, err_msg = _collect_candidates_by_prefix(source_paths, search_dirs, log)
    if not candidates:
        return [], err_msg

    return _asset_match(source_paths, candidates, log)


def find_target_bundles_by_core(
    source_paths: list[Path],
    game_resource_dir: Path | list[Path],
    log: LogFunc = no_log,
) -> tuple[list[Path], str]:
    """
    根据源文件组，在游戏资源目录中智能查找对应的目标文件组（通过 core 匹配）。

    Returns:
        tuple[list[Path], str]: (找到的目标路径列表, 状态消息)
    """
    if not source_paths:
        return [], t("message.search.check_file_exists", path="[]")

    log(t("log.search.searching_for_file_group", count=len(source_paths)))

    search_dirs = [game_resource_dir] if isinstance(game_resource_dir, Path) else game_resource_dir

    candidates, err_msg = _collect_candidates_by_core(source_paths, search_dirs, log)
    if not candidates:
        return [], err_msg

    return _asset_match(source_paths, candidates, log)