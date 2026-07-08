# adb/manager.py
"""ADB 连接与命令执行管理器"""

import subprocess
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..i18n import t
from ..utils import CREATE_NO_WINDOW, no_log


class ADBError(Exception):
    """ADB 操作错误"""
    pass


@dataclass
class ADBDevice:
    """ADB 设备信息"""
    serial: str       # 设备序列号
    state: str        # device / offline / unauthorized
    model: str        # 设备型号

    @property
    def is_ready(self) -> bool:
        return self.state == "device"

    @property
    def display_name(self) -> str:
        """显示名称: 序列号 (型号)"""
        if self.model:
            return f"{self.serial} ({self.model})"
        return self.serial


class ADBManager:
    """ADB 连接与命令执行管理器"""

    def __init__(self, adb_path: str = "adb"):
        self.adb_path = adb_path
        self._device: str | None = None

    @property
    def current_device(self) -> str | None:
        """当前选中的设备序列号"""
        return self._device

    @property
    def is_connected(self) -> bool:
        """当前设备是否真正在线（实时检查）"""
        # 实时检查设备列表
        try:
            result = self._run_command(["devices"])
        except ADBError:
            return False

        online_devices: list[str] = []
        for line in result.stdout.strip().splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                online_devices.append(parts[0])

        # 当前设备仍在线
        if self._device is not None and self._device in online_devices:
            return True

        # 当前设备已断开，尝试自动选择第一个可用设备
        if online_devices:
            self._device = online_devices[0]
            return True

        # 无可用设备
        self._device = None
        return False

    # --- 设备管理 ---

    def get_devices(self) -> list[ADBDevice]:
        """获取已连接设备列表"""
        try:
            result = self._run_command(["devices", "-l"])
        except ADBError:
            return []

        devices: list[ADBDevice] = []
        for line in result.stdout.strip().splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial = parts[0]
            state = parts[1]
            # 解析型号: model:XXX
            model = ""
            for part in parts[2:]:
                if part.startswith("model:"):
                    model = part[6:]
                    break
            devices.append(ADBDevice(serial=serial, state=state, model=model))

        return devices

    def select_device(self, serial: str) -> bool:
        """选择设备，验证连接状态"""
        devices = self.get_devices()
        for d in devices:
            if d.serial == serial and d.is_ready:
                self._device = serial
                return True
        return False

    def try_reconnect(self, serial: str | None = None) -> bool:
        """尝试重新连接设备"""
        target = serial or self._device
        if not target:
            return False
        return self.select_device(target)

    # --- 检测 ---

    def detect_adb(self) -> tuple[bool, str]:
        """检测 ADB 是否可用
        Returns: (是否可用, 版本信息或错误消息)
        """
        try:
            result = self._run_command(["version"])
            version_line = result.stdout.strip().splitlines()[0]
            return True, version_line
        except ADBError as e:
            return False, str(e)

    # --- 文件操作 ---

    def list_dir(self, remote_path: str, log=no_log) -> list[dict]:
        """列出远程目录内容

        Returns: [{"name": str, "size": int, "mtime": float, "is_dir": bool}, ...]
        """
        # 使用 ls -la 获取详细信息
        cmd = ["shell", "ls", "-la", remote_path]
        try:
            result = self._run_command(cmd, timeout=30)
        except ADBError as e:
            log(t("log.adb.list_dir_failed", path=remote_path, error=e))
            return []

        entries: list[dict] = []
        for line in result.stdout.strip().splitlines():
            entry = self._parse_ls_line(line)
            if entry and entry["name"] not in (".", ".."):
                entries.append(entry)

        return entries

    def pull_file(self, remote_path: str, local_path: Path, log=no_log) -> bool:
        """从设备拉取文件"""
        local_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["pull", remote_path, str(local_path)]
        try:
            result = self._run_command(cmd, timeout=120)
            if result.returncode != 0:
                log(t("log.adb.pull_failed", path=remote_path, error=result.stderr.strip()))
                return False
            return True
        except ADBError as e:
            log(t("log.adb.pull_failed", path=remote_path, error=e))
            return False

    def push_file(self, local_path: Path, remote_path: str, log=no_log) -> bool:
        """推送文件到设备"""
        cmd = ["push", str(local_path), remote_path]
        try:
            result = self._run_command(cmd, timeout=120)
            if result.returncode != 0:
                log(t("log.adb.push_failed", path=remote_path, error=result.stderr.strip()))
                return False
            return True
        except ADBError as e:
            log(t("log.adb.push_failed", path=remote_path, error=e))
            return False

    def file_exists(self, remote_path: str) -> bool:
        """检查远程文件是否存在"""
        cmd = ["shell", "test", "-e", remote_path, "&&", "echo", "1"]
        try:
            result = self._run_command(cmd, timeout=10)
            return "1" in result.stdout
        except ADBError:
            return False

    def get_file_size(self, remote_path: str) -> int | None:
        """获取远程文件大小"""
        cmd = ["shell", "stat", "-c", "%s", remote_path]
        try:
            result = self._run_command(cmd, timeout=10)
            return int(result.stdout.strip())
        except (ADBError, ValueError):
            return None

    # --- 底层命令 ---

    def _run_command(self, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
        """执行 ADB 命令，统一错误处理"""
        full_args = [self.adb_path]
        # 如果已选择设备，添加 -s serial
        if self._device and args[0] not in ("devices", "version", "start-server", "kill-server"):
            full_args += ["-s", self._device]
        full_args += args

        try:
            result = subprocess.run(
                full_args,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
                creationflags=CREATE_NO_WINDOW,
            )
            return result
        except FileNotFoundError:
            raise ADBError(f"ADB executable not found: {self.adb_path}")
        except subprocess.TimeoutExpired:
            raise ADBError(f"ADB command timeout ({timeout}s)")

    @staticmethod
    def _parse_ls_line(line: str) -> dict | None:
        """解析 ls -la 输出行

        格式示例:
        drwxrwx--x 3 root root 4096 2024-01-15 10:30 .
        -rw-rw---- 1 root root 1234567 2024-01-15 10:30 file.bundle
        """
        line = line.strip()
        if not line:
            return None

        # 匹配权限位开头
        if not re.match(r'^[dlcbps-]', line):
            return None

        parts = line.split()
        if len(parts) < 6:
            return None

        perms = parts[0]
        name = parts[-1]
        is_dir = perms.startswith("d")

        size = 0
        mtime = 0.0

        # 尝试解析大小（第5列）和日期时间
        try:
            size = int(parts[4])
        except (ValueError, IndexError):
            pass

        try:
            # 日期格式: 2024-01-15 10:30
            date_str = f"{parts[5]} {parts[6]}"
            from datetime import datetime
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
            mtime = dt.timestamp()
        except (ValueError, IndexError):
            pass

        return {"name": name, "size": size, "mtime": mtime, "is_dir": is_dir}
