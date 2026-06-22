# adb/file_source.py
"""文件源适配器 — 统一本地与 ADB 文件操作接口"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from ..i18n import t
from ..utils import no_log
from ..models import BundleFileInfo
from .manager import ADBManager
from .index import ADBFileIndex, RemoteFileInfo
from .cache import ADBCache
from .paths import get_adb_search_dirs, get_adb_base_path


class FileSourceAdapter(ABC):
    """文件源适配器基类 — 统一本地与 ADB 文件操作接口"""

    @abstractmethod
    def list_files(self, directory: str, suffix: str = ".bundle",
                   log=no_log) -> list[BundleFileInfo]:
        """列出目录下指定后缀的文件"""

    @abstractmethod
    def ensure_local(self, path: str) -> Path:
        """确保文件在本地可用，返回本地 Path"""

    @abstractmethod
    def push_file(self, local_path: Path, remote_path: str, log=no_log) -> bool:
        """推送本地文件到远程（仅 ADB 模式有意义）"""

    @abstractmethod
    def get_search_dirs(self, base_dir: str = "") -> list[str]:
        """获取搜索目录列表"""

    @abstractmethod
    def is_available(self) -> bool:
        """文件源是否可用"""

    @abstractmethod
    def source_name(self) -> str:
        """文件源名称标识: "local" | "adb" """


class LocalFileSource(FileSourceAdapter):
    """本地文件系统适配器"""

    def list_files(self, directory: str, suffix: str = ".bundle",
                   log=no_log) -> list[BundleFileInfo]:
        dir_path = Path(directory)
        if not dir_path.is_dir():
            return []
        results: list[BundleFileInfo] = []
        seen: set[Path] = set()
        for f in sorted(dir_path.iterdir()):
            if not f.is_file() or f.suffix != suffix:
                continue
            if f in seen:
                continue
            seen.add(f)
            stat = f.stat()
            results.append(BundleFileInfo(
                path=f,
                file_size=stat.st_size,
                modified_time=stat.st_mtime,
                source="local",
            ))
        return results

    def ensure_local(self, path: str) -> Path:
        return Path(path)

    def push_file(self, local_path: Path, remote_path: str, log=no_log) -> bool:
        return True  # 本地模式无需推送

    def get_search_dirs(self, base_dir: str = "") -> list[str]:
        from ..searching import get_search_dirs
        if not base_dir:
            return []
        return [str(p) for p in get_search_dirs(Path(base_dir))]

    def is_available(self) -> bool:
        return True

    def source_name(self) -> str:
        return "local"


class ADBFileSource(FileSourceAdapter):
    """ADB 文件源适配器"""

    def __init__(self, adb_manager: ADBManager, file_index: ADBFileIndex,
                 cache: ADBCache, server_region: str = "global"):
        self.adb_manager = adb_manager
        self.file_index = file_index
        self.cache = cache
        self.server_region = server_region

    def list_files(self, directory: str, suffix: str = ".bundle",
                   log=no_log) -> list[BundleFileInfo]:
        remote_files = self.file_index.find_files_by_suffix(directory, suffix, log=log)
        results: list[BundleFileInfo] = []
        seen: set[str] = set()
        for f in remote_files:
            if f.path in seen:
                continue
            seen.add(f.path)
            results.append(BundleFileInfo(
                path=Path(f.path),
                file_size=f.size,
                modified_time=f.modified_time,
                source="adb",
            ))
        return results

    def ensure_local(self, path: str) -> Path:
        """确保远程文件在本地可用，返回本地缓存路径"""
        # ADB 远程路径始终使用正斜杠，Windows Path 会转为反斜杠，需要还原
        remote_path = path.replace("\\", "/")
        return self.cache.ensure_cached(remote_path, self.adb_manager)

    def push_file(self, local_path: Path, remote_path: str, log=no_log) -> bool:
        result = self.adb_manager.push_file(local_path, remote_path, log)
        if result:
            self.file_index.invalidate()  # 推送后刷新索引
            self.cache.invalidate(remote_path, log=log)  # 推送后缓存失效
        return result

    def get_search_dirs(self, base_dir: str = "") -> list[str]:
        """根据区服返回 Android 资源目录"""
        return get_adb_search_dirs(self.server_region)

    def get_base_path(self) -> str:
        """根据区服返回 ADB 基础路径（浏览器起始目录）"""
        return get_adb_base_path(self.server_region)

    def is_available(self) -> bool:
        return self.adb_manager.is_connected

    def source_name(self) -> str:
        return "adb"

    def find_files_by_prefix(self, remote_dir: str, prefix: str,
                             suffix: str = ".bundle", log=no_log) -> list[RemoteFileInfo]:
        """按前缀查找远程文件"""
        return self.file_index.find_files_by_prefix(remote_dir, prefix, suffix, log=log)

    def refresh_index(self, log=no_log):
        """强制刷新所有索引"""
        search_dirs = self.get_search_dirs()
        for d in search_dirs:
            self.file_index.list_files(d, force_refresh=True, log=log)
