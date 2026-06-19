# adb/__init__.py
"""ADB 集成模块 — 提供安卓设备文件访问能力"""

from .manager import ADBManager, ADBDevice, ADBError
from .index import ADBFileIndex, RemoteFileInfo
from .cache import ADBCache, CacheEntry
from .file_source import FileSourceAdapter, LocalFileSource, ADBFileSource
from .paths import ADB_PATHS, ADB_BASE_PATHS, ADBServerRegion

__all__ = [
    "ADBManager", "ADBDevice", "ADBError",
    "ADBFileIndex", "RemoteFileInfo",
    "ADBCache", "CacheEntry",
    "FileSourceAdapter", "LocalFileSource", "ADBFileSource",
    "ADB_PATHS", "ADB_BASE_PATHS", "ADBServerRegion",
]
