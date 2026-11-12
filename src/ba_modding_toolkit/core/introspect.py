# core/introspect.py
"""只读诊断：bundle 内省（inspect）与引用追踪（trace）。

CLI 专属命令的后端逻辑，英文输出、不走 i18n。
"""

from collections import Counter
from pathlib import Path
from typing import Callable
import os

from ..bundle import Bundle, get_cab_names
from ..models import LogFunc
from ..references import BundleGraph, iter_pptrs, reference
from ..searching import find_cab_bundles, get_search_dirs
from ..utils import no_log


def _resolve_game_dirs(resource_dir: Path | None) -> list[Path]:
    """游戏资源根目录 → 实际存在的搜索目录列表"""
    return get_search_dirs(resource_dir) if resource_dir else []


def _collect_externals(bundle: Bundle) -> set[str]:
    """收集 bundle 内全部 SerializedFile 的外部 CAB 名"""
    cabs: set[str] = set()
    for sf in bundle.env.assets:
        for ext in sf.externals:
            cabs.add(ext.path.replace("\\", "/").rsplit("/", 1)[-1])
    return cabs


def _self_cabs(bundle: Bundle) -> list[str]:
    """收集 bundle 内全部 SerializedFile 的自身 CAB 名（多 SF bundle 取全部）"""
    names = [getattr(sf, "name", "") for sf in bundle.env.assets]
    return [name for name in names if name]


def _build_full_index(search_dirs: list[Path], log: LogFunc) -> dict[str, Path]:
    """全量 CAB 索引：轻量解析所有 bundle 的头部文件名表（秒级，不解压数据块）"""
    index: dict[str, Path] = {}
    for dir in search_dirs:
        if not dir.is_dir():
            continue
        with os.scandir(dir) as it:
            for entry in it:
                if not entry.name.endswith('.bundle') or not entry.is_file(follow_symlinks=False):
                    continue
                names = get_cab_names(Path(entry.path))
                if names:
                    for cab in names:
                        index.setdefault(cab, Path(entry.path))
    log(f"  > Full CAB index built: {len(index)} CAB(s).")
    return index


def _make_graph(
    bundles: list[Bundle],
    search_dirs: list[Path],
    log: LogFunc,
    cache_path: Path | None,
) -> BundleGraph:
    """为给定 bundle 组构建可跨包解析的对象图。

    先按目标 bundle 的 externals 用 find_cab_bundles 定位（同组优先 → prolog → 全量兜底，
    带缓存），再挂一个"全量索引"fallback 兜底，覆盖间接引用的 CAB。
    """
    cabs: set[str] = set()
    for bundle in bundles:
        cabs |= _collect_externals(bundle)

    index: dict[str, Path] = {}
    if search_dirs and cabs:
        # 同组先验以第一个 bundle 为准（多 bundle 时组名可能不同，但取其一即可受益）
        index = find_cab_bundles(cabs, search_dirs, log, cache_path=cache_path,
                                 hint_path=bundles[0].path)

    fallback: Callable[[], dict[str, Path]] | None = None
    if search_dirs:
        def fallback() -> dict[str, Path]:
            log("  > CAB not in index, building full CAB index...")
            return _build_full_index(search_dirs, log)

    graph = BundleGraph(index, fallback=fallback, log=log)
    for bundle in bundles:
        graph.add(bundle.path)
    return graph


def _obj_name(obj) -> str:
    """安全取名，失败返回空串"""
    try:
        return obj.peek_name() or ""
    except Exception:
        return ""


def inspect_bundles(
    bundle_paths: list[Path],
    log: LogFunc = no_log,
    resource_dir: Path | None = None,
    cache_path: Path | None = None,
    local_only: bool = False,
) -> None:
    """输出 bundle 内省信息：平台、自身 CAB、类型统计、外部引用、MonoBehaviour 清单、容器条目。"""
    search_dirs = [] if local_only else _resolve_game_dirs(resource_dir)

    bundles: list[Bundle] = []
    for path in bundle_paths:
        bundle = Bundle.load(path, log)
        if bundle is None:
            log(f"❌ Failed to load: {path}")
            continue
        bundles.append(bundle)
    if not bundles:
        return

    graph = _make_graph(bundles, search_dirs, log, cache_path)

    for bundle in bundles:
        log(f"\n=== {bundle.path.name} ===")
        platform, unity_version = bundle.platform_info
        log(f"Platform: {platform} | Unity: {unity_version}")
        self_cabs = _self_cabs(bundle)
        if self_cabs:
            log(f"Self CAB: {', '.join(self_cabs)}")

        objects = list(bundle.env.objects)
        if not objects:
            log("(empty bundle)")
            continue

        # 类型统计
        log(f"Objects: {len(objects)}")
        for type_name, count in Counter(obj.type.name for obj in objects).most_common():
            log(f"  {type_name}: {count}")

        # 外部引用
        externals = sorted(_collect_externals(bundle))
        log(f"External references ({len(externals)}):")
        for cab in externals:
            target = graph.index.get(cab.lower())
            if target:
                suffix = f" -> {Path(target).name}"
            elif local_only:
                suffix = " [unresolved (local-only)]"
            else:
                suffix = ""
            log(f"  - {cab}{suffix}")

        # MonoBehaviour 按 MonoScript 类名分组
        behaviours = [obj for obj in objects if obj.type.name == "MonoBehaviour"]
        if behaviours:
            log(f"MonoBehaviour ({len(behaviours)}):")
            groups: dict[str, list] = {}
            for obj in behaviours:
                try:
                    class_name = graph.script(obj) or "(unknown script)"
                except Exception as e:
                    class_name = f"(script resolve failed: {e})"
                groups.setdefault(class_name, []).append(obj)
            for class_name, objs in sorted(groups.items()):
                log(f"  [{class_name}] x{len(objs)}")
                for obj in objs:
                    name = _obj_name(obj)
                    log(f"    - {name} (path_id {obj.path_id})" if name else f"    - (path_id {obj.path_id})")

        # 容器条目
        container = bundle.env.container
        if container:
            log(f"Container ({len(container)}):")
            for container_path, obj in container.items():
                log(f"  - {container_path} [{obj.type.name}] (path_id {obj.path_id})")


def trace_bundle(
    bundle_path: Path,
    log: LogFunc = no_log,
    path_id: int | None = None,
    resource_dir: Path | None = None,
    cache_path: Path | None = None,
    local_only: bool = False,
) -> None:
    """追踪 bundle 内对象的全部引用，解析每个指针的落点。

    Args:
        bundle_path: 目标 bundle 文件
        path_id: 只追踪指定 path_id 的对象；None 表示追踪全部对象
        resource_dir: 游戏资源根目录（用于跨包解析；不提供则仅限本地与索引内解析）
        cache_path: CAB 映射缓存文件路径
        local_only: 仅本地解析，跳过跨包定位（未解析指针标注 local-only）
    """
    bundle = Bundle.load(bundle_path, log)
    if bundle is None:
        log(f"❌ Failed to load: {bundle_path}")
        return

    search_dirs = [] if local_only else _resolve_game_dirs(resource_dir)
    graph = _make_graph([bundle], search_dirs, log, cache_path)

    objects = list(bundle.env.objects)
    if path_id is not None:
        objects = [obj for obj in objects if obj.path_id == path_id]
        if not objects:
            log(f"❌ Object with path_id {path_id} not found in {bundle_path.name}.")
            return

    log(f"=== {bundle_path.name} ===")
    self_cabs = _self_cabs(bundle)
    if self_cabs:
        log(f"Self CAB: {', '.join(self_cabs)}")
    resolved = missing = 0
    for obj in objects:
        try:
            tree = graph.tree(obj)
        except Exception:
            continue  # 无 typetree 的对象跳过
        # 去重后输出该对象的全部引用（保留原始指针以走懒加载）
        seen: set[tuple[str, int]] = set()
        refs: list[tuple[tuple[str, int], dict[str, int]]] = []
        for pointer in iter_pptrs(tree):
            cab, pid = reference(obj, pointer)
            if pid == 0 or (cab, pid) in seen:
                continue
            seen.add((cab, pid))
            refs.append(((cab, pid), pointer))
        if not refs:
            continue

        name = _obj_name(obj)
        header = f"{obj.type.name} '{name}'" if name else obj.type.name
        log(f"\n{header} (path_id {obj.path_id}) -> {len(refs)} reference(s):")
        for (cab, pid), pointer in refs:
            target = graph.deref(obj, pointer)
            if target is None:
                missing += 1
                suffix = " (unresolved (local-only))" if local_only else " (unresolved)"
                log(f"  -> {cab}:{pid}{suffix}")
            else:
                resolved += 1
                target_name = _obj_name(target)
                loc = graph.index.get(cab.lower())
                if cab == obj.assets_file.name:
                    loc_suffix = " (same file)"
                elif loc:
                    loc_suffix = f" [{Path(loc).name}]"
                else:
                    loc_suffix = ""
                shown = f" '{target_name}'" if target_name else ""
                log(f"  -> {cab}:{pid} = {target.type.name}{shown}{loc_suffix}")

    log(f"\nDone: {resolved} resolved, {missing} unresolved.")
