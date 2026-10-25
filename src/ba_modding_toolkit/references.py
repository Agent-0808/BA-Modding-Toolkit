# references.py
"""跨 bundle 指针解析：typetree PPtr → CAB 名 → 目标对象。

提供三块领域无关的能力：
- reference(): 把 typetree 指针 (m_FileID, m_PathID) 解析为 (CAB 名, path_id)
- iter_pptrs(): 递归遍历 typetree 中的全部 PPtr 指针
- BundleGraph: 懒加载的跨 bundle 对象图，deref() 时按需加载目标 bundle
"""

from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any, Callable

from UnityPy.files import ObjectReader

from .bundle import Bundle, get_cab_names
from .models import LogFunc
from .utils import no_log


def reference(obj: ObjectReader, pointer: Mapping[str, int]) -> tuple[str, int]:
    """把 typetree 指针解析为 (CAB 名, path_id)。

    m_FileID == 0 表示同文件内引用，CAB 名取自身所在 SerializedFile；
    非 0 时按 externals 表（1-based）查引用文件的 CAB 名。
    """
    fid = pointer.get("m_FileID", 0)
    cab = obj.assets_file.name if fid == 0 else obj.assets_file.externals[fid - 1].path.replace("\\", "/").rsplit("/", 1)[-1]
    return cab, pointer.get("m_PathID", 0)


def iter_pptrs(value: Any) -> Iterator[dict[str, int]]:
    """递归遍历 typetree 值中的全部 PPtr 指针（{"m_FileID": int, "m_PathID": int}）。

    Unity 的 PPtr 固定含 m_FileID 与 m_PathID 两个键，以此特征识别，
    不依赖具体对象类型。
    """
    if isinstance(value, dict):
        if "m_FileID" in value and "m_PathID" in value:
            yield value
        else:
            for v in value.values():
                yield from iter_pptrs(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from iter_pptrs(v)


def _external_cab(obj: ObjectReader, file_id: int) -> str:
    """获取指针目标 CAB 名（小写，作为图内统一键）"""
    if file_id == 0:
        return obj.assets_file.name.lower()
    return obj.assets_file.externals[file_id - 1].path.replace("\\", "/").rsplit("/", 1)[-1].lower()


class BundleGraph:
    """以 (CAB 名, path_id) 为键的懒加载跨 bundle 对象图。

    deref() 遇到未加载的 CAB 时按 index 定位并加载其所在 bundle，
    因此只读取真正被引用到的 bundle。index 缺失时可提供 fallback
    回调，在首次未命中时构建一次全量 CAB 索引（bundle 覆盖索引优先）。
    overrides 中的 bundle（mod 产物）会接管其持有的 CAB，实现
    "mod 资源优先"的解析语义。

    仅限单线程使用（CLI 命令内）。Bundle.load 将数据读入内存、
    不保留文件句柄，无需显式关闭。
    """

    def __init__(
        self,
        index: Mapping[str, Path | str],
        overrides: Iterable[Path] = (),
        *,
        fallback: Callable[[], Mapping[str, Path | str]] | None = None,
        log: LogFunc = no_log,
    ):
        self.index: dict[str, str] = {cab.lower(): str(path) for cab, path in index.items()}
        for path in overrides:
            names = get_cab_names(Path(path))
            if names:
                for cab in names:
                    self.index[cab.lower()] = str(path)
        self.fallback = fallback
        self.log = log
        self.objects: dict[tuple[str, int], ObjectReader] = {}
        self.trees: dict[tuple[str, int], Any] = {}
        self.loaded: list[str] = []

    def add(self, path: Path | str) -> Bundle | None:
        """加载一个 bundle 并索引其全部对象；已加载过则返回 None"""
        path = str(path)
        if path in self.loaded:
            return None
        self.loaded.append(path)
        bundle = Bundle.load(Path(path), self.log)
        if bundle is not None:
            for obj in bundle.env.objects:
                self.objects[(obj.assets_file.name.lower(), obj.path_id)] = obj
        return bundle

    def tree(self, obj: ObjectReader) -> Any:
        """读取对象的 typetree（带缓存）"""
        key = (obj.assets_file.name.lower(), obj.path_id)
        tree = self.trees.get(key)
        if tree is None:
            tree = self.trees[key] = obj.read_typetree()
        return tree

    def deref(self, obj: ObjectReader | None, pointer: Mapping[str, int] | None) -> ObjectReader | None:
        """解析指针指向的对象；目标未加载时按 index 懒加载其所在 bundle"""
        if obj is None or not pointer or not pointer.get("m_PathID"):
            return None
        cab, pid = _external_cab(obj, pointer.get("m_FileID", 0)), pointer["m_PathID"]
        hit = self.objects.get((cab, pid))
        if hit is None:
            if cab not in self.index and self.fallback is not None and cab.startswith("cab-"):
                wider = self.fallback()
                self.index = {**{c.lower(): str(p) for c, p in wider.items()}, **self.index}
                self.fallback = None  # 只扩展一次
            path = self.index.get(cab)
            if path is not None and path not in self.loaded:
                self.add(path)
                hit = self.objects.get((cab, pid))
        return hit

    def script(self, behaviour: ObjectReader) -> str | None:
        """解析 MonoBehaviour 的 MonoScript 类名（可跨 bundle）"""
        script = self.deref(behaviour, self.tree(behaviour).get("m_Script"))
        return self.tree(script).get("m_ClassName") if script is not None else None
