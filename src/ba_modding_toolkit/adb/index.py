# adb/index.py
"""ADB 远程文件索引 — 缓存设备端文件列表以避免重复扫描"""

import time
import threading
from dataclasses import dataclass
from typing import Callable

from ..i18n import t
from ..utils import no_log
from .manager import ADBManager


@dataclass
class RemoteFileInfo:
    """远程文件信息"""
    path: str              # 远程完整路径
    name: str              # 文件名
    size: int              # 文件大小（字节）
    modified_time: float   # 修改时间戳
    is_dir: bool           # 是否为目录

    def matches_prefix(self, prefix: str) -> bool:
        return self.name.startswith(prefix)

    def matches_suffix(self, suffix: str) -> bool:
        return self.name.endswith(suffix)


class ADBFileIndex:
    """ADB 远程文件索引，缓存设备端文件列表"""

    DEFAULT_TTL = 300.0  # 索引有效期（秒），默认5分钟

    def __init__(self, adb_manager: ADBManager, ttl: float | None = None):
        self._adb = adb_manager
        self._ttl = ttl or self.DEFAULT_TTL
        self._index: dict[str, list[RemoteFileInfo]] = {}
        self._index_time: dict[str, float] = {}
        self._lock = threading.Lock()

    def list_files(self, remote_dir: str, force_refresh: bool = False, log=no_log) -> list[RemoteFileInfo]:
        """列出目录文件，优先使用缓存索引

        Args:
            remote_dir: 远程目录路径
            force_refresh: 是否强制刷新
            log: 日志函数
        """
        with self._lock:
            if not force_refresh and self._is_cache_valid(remote_dir):
                return self._index.get(remote_dir, [])

        # 缓存无效或强制刷新，从设备获取
        entries = self._adb.list_dir(remote_dir, log)

        files: list[RemoteFileInfo] = []
        for entry in entries:
            remote_path = remote_dir.rstrip("/") + "/" + entry["name"]
            files.append(RemoteFileInfo(
                path=remote_path,
                name=entry["name"],
                size=entry.get("size", 0),
                modified_time=entry.get("mtime", 0.0),
                is_dir=entry.get("is_dir", False),
            ))

        with self._lock:
            self._index[remote_dir] = files
            self._index_time[remote_dir] = time.time()

        return files

    def find_files_by_prefix(self, remote_dir: str, prefix: str,
                             suffix: str = ".bundle", log=no_log) -> list[RemoteFileInfo]:
        """按前缀查找文件（用于 search_prefix 适配）"""
        files = self.list_files(remote_dir, log=log)
        return [
            f for f in files
            if not f.is_dir and f.matches_prefix(prefix) and f.matches_suffix(suffix)
        ]

    def find_files_by_suffix(self, remote_dir: str, suffix: str = ".bundle",
                             log=no_log) -> list[RemoteFileInfo]:
        """按后缀查找文件"""
        files = self.list_files(remote_dir, log=log)
        return [f for f in files if not f.is_dir and f.matches_suffix(suffix)]

    def invalidate(self, remote_dir: str | None = None):
        """使索引失效

        Args:
            remote_dir: 指定目录失效，None 则全量失效
        """
        with self._lock:
            if remote_dir is None:
                self._index.clear()
                self._index_time.clear()
            else:
                self._index.pop(remote_dir, None)
                self._index_time.pop(remote_dir, None)

    def _is_cache_valid(self, remote_dir: str) -> bool:
        """检查缓存是否在有效期内"""
        if remote_dir not in self._index_time:
            return False
        return (time.time() - self._index_time[remote_dir]) < self._ttl
