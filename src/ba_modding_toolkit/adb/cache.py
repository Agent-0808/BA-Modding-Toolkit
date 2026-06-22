# adb/cache.py
"""ADB 文件本地缓存管理器"""

import json
import time
import threading
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable

from ..i18n import t
from ..utils import no_log
from .manager import ADBManager
from .paths import get_adb_package_name


@dataclass
class CacheEntry:
    """缓存条目"""
    remote_path: str       # 远程路径
    local_path: str        # 本地缓存路径（相对路径）
    remote_size: int       # 远程文件大小
    remote_mtime: float    # 远程修改时间
    cached_time: float     # 缓存时间


class ADBCache:
    """ADB 文件本地缓存管理器"""

    MANIFEST_FILE = "manifest.json"

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or self._default_cache_dir()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._manifest: dict[str, CacheEntry] = {}  # remote_path -> CacheEntry
        self._lock = threading.Lock()
        self._load_manifest()

    @staticmethod
    def _default_cache_dir() -> Path:
        """默认缓存目录"""
        # 使用用户临时目录
        import tempfile
        return Path(tempfile.gettempdir()) / "bamt_adb_cache"

    def get_local_path(self, remote_path: str) -> Path | None:
        """获取缓存文件路径，若缓存有效则返回本地路径"""
        with self._lock:
            entry = self._manifest.get(remote_path)
            if entry is None:
                return None
            local = self.cache_dir / entry.local_path
            if local.exists() and local.stat().st_size == entry.remote_size:
                return local
            return None

    def ensure_cached(self, remote_path: str, adb_manager: ADBManager,
                      log=no_log) -> Path:
        """确保远程文件已缓存到本地，返回本地路径

        若缓存命中且校验通过，直接返回。
        若缓存未命中或已失效，从设备拉取。
        """
        # 检查缓存
        cached = self.get_local_path(remote_path)
        if cached is not None:
            log(t("log.adb.cache_hit", name=Path(remote_path).name))
            return cached

        # 缓存未命中，拉取
        local_path = self._get_cache_path(remote_path)
        log(t("log.adb.cache_miss", name=Path(remote_path).name))

        success = adb_manager.pull_file(remote_path, local_path, log)
        if not success:
            raise RuntimeError(f"Failed to cache file from device: {Path(remote_path).name}")

        # 获取远程文件信息用于校验
        remote_size = adb_manager.get_file_size(remote_path) or local_path.stat().st_size

        # 更新清单
        entry = CacheEntry(
            remote_path=remote_path,
            local_path=str(local_path.relative_to(self.cache_dir)),
            remote_size=remote_size,
            remote_mtime=0.0,  # mtime 在 list_dir 时已获取
            cached_time=time.time(),
        )
        with self._lock:
            self._manifest[remote_path] = entry
            self._save_manifest()

        return local_path

    def find_remote_path(self, local_path: Path) -> str | None:
        """根据本地缓存路径反查远程路径"""
        try:
            relative = str(local_path.relative_to(self.cache_dir)).replace("\\", "/")
        except ValueError:
            return None
        with self._lock:
            for remote_path, entry in self._manifest.items():
                if entry.local_path.replace("\\", "/") == relative:
                    return remote_path
        return None

    def invalidate(self, remote_path: str | None = None, log=no_log):
        """使缓存失效"""
        with self._lock:
            if remote_path is None:
                # 全量失效
                self._manifest.clear()
            else:
                entry = self._manifest.pop(remote_path, None)
                if entry:
                    local = self.cache_dir / entry.local_path
                    if local.exists():
                        try:
                            local.unlink()
                        except Exception as e:
                            # 文件被占用，忽略删除失败
                            log(t("log.adb.cache_delete_failed", name=Path(remote_path).name, error=str(e)))
                            pass
            self._save_manifest()

    def get_cache_size(self) -> int:
        """获取缓存总大小（字节）"""
        total = 0
        for entry in self._manifest.values():
            local = self.cache_dir / entry.local_path
            if local.exists():
                total += local.stat().st_size
        return total

    def get_cache_size_display(self) -> str:
        """获取缓存大小的可读字符串"""
        size = self.get_cache_size()
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"

    def clear_cache(self) -> tuple[bool, str]:
        """清理全部缓存

        Returns: (是否成功, 释放空间描述)
        """
        freed_size = self.get_cache_size()
        with self._lock:
            self._manifest.clear()
            self._save_manifest()

        # 删除缓存文件但保留目录和 manifest
        for item in self.cache_dir.iterdir():
            if item.name != self.MANIFEST_FILE:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)

        freed_display = self._format_size(freed_size)
        return True, freed_display

    def _get_cache_path(self, remote_path: str) -> Path:
        """将远程路径映射为本地缓存路径

        例: /storage/emulated/0/Android/data/com.nexon.bluearchive/.../bundle_name.bundle
         -> cache_dir/com.nexon.bluearchive/GameData/Android/bundle_name.bundle
        """
        # 确保使用正斜杠（Windows Path 可能引入反斜杠）
        path = remote_path.replace("\\", "/")
        for pkg in ("com.nexon.bluearchive", "com.Yostar JP.BlueArchive"):
            idx = path.find(pkg)
            if idx >= 0:
                # 从包名开始截取，使用正斜杠构建本地相对路径
                relative = path[idx + len(pkg):].lstrip("/")
                return self.cache_dir / pkg / relative

        # 无法识别包名，使用完整路径的哈希
        import hashlib
        h = hashlib.md5(remote_path.encode()).hexdigest()[:8]
        name = Path(remote_path).name
        return self.cache_dir / h / name

    def _load_manifest(self):
        """从 manifest.json 加载缓存清单"""
        manifest_path = self.cache_dir / self.MANIFEST_FILE
        if not manifest_path.exists():
            return

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key, val in data.items():
                self._manifest[key] = CacheEntry(**val)
        except (json.JSONDecodeError, TypeError, KeyError):
            # 清单损坏，忽略
            self._manifest.clear()

    def _save_manifest(self):
        """保存缓存清单到 manifest.json"""
        manifest_path = self.cache_dir / self.MANIFEST_FILE
        try:
            data = {k: asdict(v) for k, v in self._manifest.items()}
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    @staticmethod
    def _format_size(size: int) -> str:
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"
