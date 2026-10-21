# utils/paths.py
"""路径与环境定位工具 — 无内部依赖的叶子模块"""

from pathlib import Path
from typing import Literal
import sys


def _get_path_from_registry(key_path: str) -> str | None:
    """从 Windows 注册表获取 Steam 游戏的安装路径。"""

    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        install_path, _ = winreg.QueryValueEx(key, "InstallLocation")
        winreg.CloseKey(key)

        if install_path:
            return install_path

    except Exception as e:
        print(f"读取注册表 {key_path} 时出错: {e}")

    return None

_ba_path_cache: dict[str, str | None] = {}

# 游戏区服，用于定位安装路径；auto = global 优先，japan 兜底
BARegion = Literal["auto", "global", "japan"]

def get_BA_path(region: BARegion = "auto") -> str | None:
    """获取游戏安装路径，带缓存机制

    Args:
        region: 区服，"auto"（默认）时优先返回 global 的结果，找不到则回退 japan

    Returns:
        游戏安装路径，如果未找到则返回 None
    """
    if region in _ba_path_cache:
        return _ba_path_cache[region]

    if region == "global":
        BA_STEAM_APPID = 3557620
        result = _get_path_from_registry(fr"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App {BA_STEAM_APPID}")
    elif region == "japan":
        result = _get_path_from_registry(r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\e02a2fab-b426-5ce2-b9de-b9e7506c327e")
    else:  # auto
        result = get_BA_path("global") or get_BA_path("japan")
        return result  # auto 不缓存，保持对注册表变化的响应

    _ba_path_cache[region] = result
    return result

# 程序所在目录（打包后为 exe 目录，开发环境为项目根目录）
# 注意：本文件位于 src/ba_modding_toolkit/utils/ 下，比原 utils.py 深一层
EXE_DIR: Path = (
    Path(__compiled__.containing_dir).resolve()
    if "__compiled__" in globals() and hasattr(__compiled__, "containing_dir")
    else Path(__file__).resolve().parents[3]
)

# 包资源根目录（打包后为 nuitka 解压的资源目录（temp 目录下），开发环境为源码包目录 src/ba_modding_toolkit/）
PACKAGE_DIR: Path = (
    Path(sys.executable).parent / "ba_modding_toolkit"
    if "__compiled__" in globals()
    else Path(__file__).resolve().parents[1]
)
