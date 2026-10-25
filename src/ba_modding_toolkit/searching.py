# searching.py

import json
from pathlib import Path
from typing import TYPE_CHECKING
import os

from .i18n import t
from .utils import no_log
from .naming import parse_filename, parse_asset_core, get_category_prefix, PRELOAD_PREFIX
from .bundle import Bundle, BundleFileInfo, get_cab_names
from .models import LogFunc, AssetKey, AssetType

if TYPE_CHECKING:
    from .adb.file_source import ADBFileSource


def search_prefix(
    source_path: Path,
    search_dirs: list[Path],
    log: LogFunc = no_log,
) -> tuple[list[Path], str]:
    """
    通过文件名前缀(prefix)匹配，在搜索目录中收集候选目标文件。
    目标文件后缀固定为 .bundle。

    Args:
        source_path: 源文件路径
        search_dirs: 搜索目录列表
        log: 日志记录函数

    Returns:
        tuple[list[Path], str]: (候选文件路径列表, 错误消息)
        - 成功时: (candidates, "")
        - 失败时: ([], 错误消息)
    """
    prefix = parse_filename(str(source_path.name)).prefix

    if not prefix:
        msg = t("message.search.filename_parse_failed")
        log(f'  > {t("common.fail")}: {msg}')
        return [], msg

    log(f"  > {t('log.search.file_prefix', prefix=prefix)}")

    # 使用 scandir 代替 iterdir + is_file，避免海量文件时的逐个 stat 系统调用
    candidates: list[Path] = []
    for dir in search_dirs:
        if not dir.is_dir():
            continue
        with os.scandir(dir) as it:
            candidates.extend(
                Path(entry.path)
                for entry in it
                if entry.name.startswith(prefix)
                and entry.name.endswith('.bundle')
                and entry.is_file(follow_symlinks=False)
            )

    if not candidates:
        msg = t("message.search.no_matching_files_in_dir")
        log(f'  > {t("common.fail")}: {msg}')
        return [], msg

    log(f"  > {t('log.search.found_candidates', count=len(candidates))}")
    return candidates, ""


def search_core(
    source_path: Path,
    search_dirs: list[Path],
    log: LogFunc = no_log,
) -> tuple[list[Path], str]:
    """
    通过文件名核心部分(core)匹配，在搜索目录中收集候选目标文件。
    先通过字符串包含匹配进行初筛，再通过 parse_filename 确认 core 相同。
    目标文件后缀固定为 .bundle。

    Args:
        source_path: 源文件路径（散件资产，如 dump/图片/skel）
        search_dirs: 搜索目录列表
        log: 日志记录函数

    Returns:
        tuple[list[Path], str]: (候选文件路径列表, 错误消息)
    """
    # 源文件是散件资产而非 bundle，走散件命名域解析 core
    core = parse_asset_core(str(source_path.name))

    if not core:
        msg = t("message.search.filename_parse_failed")
        log(f'  > {t("common.fail")}: {msg}')
        return [], msg

    log(f"  > {t('log.search.file_core', core=core)}")

    # 字符串包含匹配，粗筛（scandir 避免逐个 stat 系统调用）
    core_lower = core.lower()
    search_prefix = get_category_prefix(core_lower)
    rough: list[Path] = []
    for dir in search_dirs:
        if not dir.is_dir():
            continue
        with os.scandir(dir) as it:
            rough.extend(
                Path(entry.path)
                for entry in it
                if entry.name.startswith(search_prefix)
                and core_lower in entry.name.lower()
                and entry.name.endswith('.bundle')
                and entry.is_file(follow_symlinks=False)
            )

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


def asset_match(
    source_paths: list[Path],
    candidates: list[Path],
    log: LogFunc = no_log,
) -> tuple[list[Path], str]:
    """
    对候选文件进行指纹比对，筛选出与源文件组匹配的目标文件。

    Returns:
        tuple[list[Path], str]: (匹配的文件路径列表, 状态消息)
    """
    comparable_types = {AssetType.Texture2D, AssetType.TextAsset, AssetType.Mesh, AssetType.AnimationClip, AssetType.Font}
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
    根据源文件组，在游戏资源目录中智能查找对应的目标文件组。
    通过第一个文件的前缀匹配。

    Returns:
        tuple[list[Path], str]: (找到的目标路径列表, 状态消息)
    """
    if not source_paths:
        return [], t("message.search.check_file_exists", path="[]")

    log(t("log.search.searching_for_file_group", count=len(source_paths)))

    search_dirs = [game_resource_dir] if isinstance(game_resource_dir, Path) else game_resource_dir

    candidates, err_msg = search_prefix(source_paths[0], search_dirs, log)
    if not candidates:
        return [], err_msg

    return asset_match(source_paths, candidates, log)


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


def list_bundle_files(base_dir: Path) -> list[BundleFileInfo]:
    """
    快速扫描搜索目录下的所有 bundle 文件，仅收集基础信息（路径、大小、修改时间）。

    Args:
        base_dir: 游戏资源根目录
        log: 日志记录函数

    Returns:
        BundleFileInfo 列表（仅基础字段已填充）
    """
    results = []
    seen = set()
    for directory in get_search_dirs(base_dir):
        with os.scandir(directory) as it:
            for entry in it:
                if not entry.is_file(follow_symlinks=False):
                    continue
                if not entry.name.endswith('.bundle'):
                    continue
                
                # 直接使用 entry.stat() 获取大小和修改时间
                st = entry.stat(follow_symlinks=False)

                bundle_path = Path(entry.path)
                if bundle_path in seen:
                    continue
                seen.add(bundle_path)
                results.append(BundleFileInfo(
                    path=bundle_path,
                    file_size=st.st_size,
                    modified_time=st.st_mtime,
                ))

    return results


def find_cab_bundles(
    target_cabs: set[str],
    search_dirs: list[Path],
    log: LogFunc = no_log,
    max_bundle_size: int = 64 * 1024 * 1024,
    cache_path: Path | None = None,
    hint_path: Path | None = None,
) -> dict[str, Path]:
    """
    在搜索目录的全部 bundle 中查找内部 SerializedFile 名（CAB-xxx）匹配的物理 bundle。

    优先用轻量头部解析（get_cab_names，不解压数据块），解析失败时回退 Bundle.load；
    扫描分三批：先扫与 hint_path 同组（parse_filename 前缀一致）的包——trace 场景的
    引用目标多为同组兄弟包；其次扫 prolog 前缀包（shaders 等公共 MonoScript 源），
    未命中时警告并回退全量扫描（大小升序）；找到全部目标后提前退出。
    提供 cache_path 时先查缓存（按路径+大小+mtime 校验有效性，不符则重扫），
    扫描结果写回缓存。

    Args:
        target_cabs: 目标 CAB 名集合（如 {"CAB-a657a..."}）
        search_dirs: 搜索目录列表
        log: 日志记录函数
        max_bundle_size: 单个 bundle 的大小上限（字节），超过则跳过
        cache_path: CAB 映射缓存文件路径；None 表示不使用缓存
        hint_path: 引用方 bundle 路径，用于派生"同组优先"扫描批次；None 表示不启用

    Returns:
        {CAB 名: 物理 bundle 路径}；未命中的 CAB 不在结果中
    """
    remaining = set(target_cabs)
    found: dict[str, Path] = {}
    if not remaining:
        return found

    # 1. 缓存命中（路径存在且大小/mtime 与记录一致）
    cache = CabCache.load(cache_path) if cache_path else None
    if cache is not None:
        cached, remaining = cache.lookup(remaining)
        found.update(cached)
        if cached:
            log(f"  > {len(cached)} CAB target(s) resolved from cache.")

    # 2. 扫描未命中的 CAB（候选按大小升序，小文件优先）
    if remaining:
        candidates: list[Path] = []
        for dir in search_dirs:
            if not dir.is_dir():
                continue
            with os.scandir(dir) as it:
                for entry in it:
                    if (entry.name.endswith('.bundle')
                            and entry.is_file(follow_symlinks=False)
                            and entry.stat(follow_symlinks=False).st_size <= max_bundle_size):
                        candidates.append(Path(entry.path))
        candidates.sort(key=lambda p: p.stat().st_size)

        def scan(batch: list[Path], label: str) -> None:
            """按大小升序扫一批 bundle，命中的 CAB 记入 found 并写回缓存"""
            nonlocal remaining
            if not remaining or not batch:
                return
            log(f"  > Scanning {len(batch)} {label} bundle(s) for {len(remaining)} CAB target(s)...")
            total = len(batch)
            progress_step = max(1, total // 20)  # 每 5% 打印一次
            for idx, bundle_path in enumerate(batch):
                if not remaining:
                    break
                if (idx + 1) % progress_step == 0 or idx + 1 == total:
                    log(f"    > Progress: {((idx + 1) * 100) // total}% ({idx + 1}/{total})")
                # 轻量解析仅读头部 blockinfo；失败时回退全量加载
                names = get_cab_names(bundle_path)
                if names is None:
                    bundle = Bundle.load(bundle_path, log)
                    if bundle is None:
                        continue
                    try:
                        names = {getattr(sf, "name", "") for sf in bundle.env.assets}
                    except Exception:
                        continue
                hit = names & remaining
                if hit:
                    for cab in hit:
                        found[cab] = bundle_path
                        remaining.discard(cab)
                        log(f"  > CAB match: {cab} -> {bundle_path.name}")
                    if cache is not None:
                        cache.update({cab: bundle_path for cab in hit})

        # 分批：同组（与引用 bundle 同 prefix）→ prolog 前缀 → 其余全量（大小升序）
        def group_key(p: Path) -> str | None:
            """同组标识 = 搜索前缀（复用 parse_filename）；无前缀的散包不参与同组批次"""
            return parse_filename(p.name).prefix or None

        batches: list[tuple[list[Path], str]] = []
        if hint_path is not None:
            hint_key = group_key(hint_path)
            if hint_key:
                batches.append(([p for p in candidates if group_key(p) == hint_key], "same-group"))
        # prolog 前缀批（naming.PRELOAD_PREFIX）：shaders 等公共 MonoScript 源常在此
        prolog_batch = [p for p in candidates if p.name.startswith(PRELOAD_PREFIX)]
        batches.append((prolog_batch, "prolog"))
        scanned = {p for batch, _ in batches for p in batch}
        batches.append(([p for p in candidates if p not in scanned], "remaining"))

        for batch, label in batches:
            if remaining and batch:
                if label == "remaining":
                    log(f"  > ⚠️ {len(remaining)} CAB target(s) not found in prior batches, "
                        f"falling back to full scan (unexpected).")
                scan(batch, label)

        if remaining:
            log(f"  > ⚠️ CAB target(s) not found: {', '.join(sorted(remaining))}")

    if cache is not None:
        cache.save()
    return found


class CabCache:
    """CAB → 物理 bundle 映射缓存（JSON 文件，按路径+大小+mtime 校验有效性）。

    游戏更新导致文件变化时校验失败、自动回退重扫并覆写条目，
    因此缓存过期只会带来一次重扫，不会返回错误映射。
    """

    CACHE_VERSION = 1

    def __init__(self, path: Path):
        self.path = path
        # {cab: {"path": str, "size": int, "mtime": float}}
        self.entries: dict[str, dict] = {}

    @classmethod
    def load(cls, path: Path) -> "CabCache":
        cache = cls(path)
        try:
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("version") == cls.CACHE_VERSION:
                    cache.entries = data.get("entries", {})
        except Exception:
            cache.entries = {}
        return cache

    def lookup(self, cabs: set[str]) -> tuple[dict[str, Path], set[str]]:
        """查询缓存，返回 (命中 {cab: path}, 未命中集合)。

        命中要求记录的文件仍存在且大小/mtime 与记录一致。
        """
        hits: dict[str, Path] = {}
        for cab in cabs:
            entry = self.entries.get(cab)
            if not entry:
                continue
            path = Path(entry["path"])
            try:
                st = path.stat()
            except OSError:
                continue
            if st.st_size == entry.get("size") and st.st_mtime == entry.get("mtime"):
                hits[cab] = path
        return hits, cabs - set(hits)

    def update(self, found: dict[str, Path]) -> None:
        """把新解析的 CAB 映射写入缓存条目"""
        for cab, path in found.items():
            st = path.stat()
            self.entries[cab] = {
                "path": str(path),
                "size": st.st_size,
                "mtime": st.st_mtime,
            }

    def save(self) -> None:
        """保存缓存文件（失败静默，缓存不可用不影响功能）"""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps({"version": self.CACHE_VERSION, "entries": self.entries}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass


# ========== ADB 远程搜索函数 ==========

def search_prefix_remote(
    source_path: Path,
    search_dirs: list[str],
    file_source: "ADBFileSource",
    log: LogFunc = no_log,
) -> tuple[list[str], str]:
    """在 ADB 远程目录中按前缀搜索文件

    Args:
        source_path: 源文件路径（本地）
        search_dirs: 远程搜索目录列表
        file_source: ADB 文件源适配器
        log: 日志函数

    Returns:
        tuple[list[str], str]: (匹配的远程路径列表, 状态消息)
    """
    prefix = parse_filename(str(source_path.name)).prefix
    extension = source_path.suffix
    if extension == '.backup':
        extension = Path(source_path.stem).suffix

    if not prefix:
        msg = t("message.search.filename_parse_failed")
        log(f'  > {t("common.fail")}: {msg}')
        return [], msg

    log(f"  > {t('log.search.file_prefix', prefix=prefix)}")

    candidates: list[str] = []
    for remote_dir in search_dirs:
        found = file_source.find_files_by_prefix(remote_dir, prefix, extension, log=log)
        candidates.extend([f.path for f in found])

    if not candidates:
        msg = t("message.search.no_matching_files_in_dir")
        log(f'  > {t("common.fail")}: {msg}')
        return [], msg

    log(f"  > {t('log.search.found_candidates', count=len(candidates))}")
    return candidates, ""


def search_core_remote(
    source_path: Path,
    search_dirs: list[str],
    file_source: "ADBFileSource",
    log: LogFunc = no_log,
) -> tuple[list[str], str]:
    """在 ADB 远程目录中按文件名核心部分(core)匹配搜索 bundle 文件

    Args:
        source_path: 源文件路径（本地，散件资产）
        search_dirs: 远程搜索目录列表
        file_source: ADB 文件源适配器
        log: 日志函数

    Returns:
        tuple[list[str], str]: (匹配的远程路径列表, 状态消息)
    """
    # 源文件是散件资产而非 bundle，走散件命名域解析 core
    core = parse_asset_core(str(source_path.name))

    if not core:
        msg = t("message.search.filename_parse_failed")
        log(f'  > {t("common.fail")}: {msg}')
        return [], msg

    log(f"  > {t('log.search.file_core', core=core)}")

    core_lower = core.lower()
    search_prefix_str = get_category_prefix(core_lower)

    # 获取所有以分类前缀开头的 bundle 文件，再按 core 过滤
    candidates: list[str] = []
    for remote_dir in search_dirs:
        # 先按前缀粗筛
        rough_files = file_source.find_files_by_prefix(
            remote_dir, search_prefix_str, ".bundle", log=log
        )
        # 再按 core 过滤（大小写不敏感）
        for f in rough_files:
            if core_lower in f.name.lower():
                file_core = parse_filename(f.name).core
                if file_core and file_core.lower() == core_lower:
                    candidates.append(f.path)

    if not candidates:
        msg = t("message.search.no_matching_files_in_dir")
        log(f'  > {t("common.fail")}: {msg}')
        return [], msg

    log(f"  > {t('log.search.found_candidates', count=len(candidates))}")
    return candidates, ""


def find_target_bundles_remote(
    source_paths: list[Path],
    file_source: "ADBFileSource",
    log: LogFunc = no_log,
) -> tuple[list[str], str]:
    """在 ADB 远程设备上查找目标文件

    Args:
        source_paths: 源文件路径列表（本地）
        file_source: ADB 文件源适配器
        log: 日志函数

    Returns:
        tuple[list[str], str]: (匹配的远程路径列表, 状态消息)
    """
    if not source_paths:
        return [], t("message.search.check_file_exists", path="[]")

    log(t("log.search.searching_for_file_group", count=len(source_paths)))

    search_dirs = file_source.get_search_dirs()

    candidates, err_msg = search_prefix_remote(source_paths[0], search_dirs, file_source, log)
    if not candidates:
        return [], err_msg

    # 指纹比对需要将候选文件拉取到本地
    local_candidates: list[Path] = []
    for remote_path in candidates:
        try:
            local_path = file_source.ensure_local(remote_path)
            local_candidates.append(local_path)
        except Exception as e:
            log(t("log.adb.pull_failed", path=remote_path, error=e))
            continue

    if not local_candidates:
        msg = t("message.search.no_matching_asset_found")
        log(f'  > {t("common.fail")}: {msg}')
        return [], msg

    matched_local, msg = asset_match(source_paths, local_candidates, log)

    # 将本地路径映射回远程路径
    local_to_remote = dict(zip(local_candidates, candidates))
    matched_remote = [local_to_remote[p] for p in matched_local if p in local_to_remote]

    return matched_remote, msg


def list_bundle_files_remote(
    file_source: "ADBFileSource",
    log: LogFunc = no_log,
) -> list[BundleFileInfo]:
    """扫描 ADB 远程设备上的 bundle 文件

    Args:
        file_source: ADB 文件源适配器
        log: 日志函数

    Returns:
        BundleFileInfo 列表
    """
    search_dirs = file_source.get_search_dirs()
    results: list[BundleFileInfo] = []
    seen: set[str] = set()

    for remote_dir in search_dirs:
        items = file_source.list_files(remote_dir, suffix=".bundle", log=log)
        for item in items:
            remote_path_str = str(item.path)
            if remote_path_str in seen:
                continue
            seen.add(remote_path_str)
            results.append(item)

    return results
