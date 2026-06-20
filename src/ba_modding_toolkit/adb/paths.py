# adb/paths.py
"""ADB 安卓区服路径常量"""

from typing import Literal

ADBServerRegion = Literal["global", "japan"]

# 各区服的 bundle 文件搜索目录（用于精确搜索）
ADB_PATHS: dict[str, list[str]] = {
    "global": [
        "/storage/emulated/0/Android/data/com.nexon.bluearchive/files/PUB/Resource/GameData/Android/",
        "/storage/emulated/0/Android/data/com.nexon.bluearchive/files/PUB/Resource/Preload/Android/",
    ],
    "japan": [
        "/storage/emulated/0/Android/data/com.Yostar JP.BlueArchive/files/AssetBundles/",
    ],
}

# 各区服的基础路径（用于浏览器起始目录和路径显示）
ADB_BASE_PATHS: dict[str, str] = {
    "global": "/storage/emulated/0/Android/data/com.nexon.bluearchive/files/PUB/Resource/",
    "japan": "/storage/emulated/0/Android/data/com.Yostar JP.BlueArchive/files/",
}


def get_adb_search_dirs(server_region: str) -> list[str]:
    """根据区服返回 ADB 资源搜索目录列表"""
    return ADB_PATHS.get(server_region, [])


def get_adb_base_path(server_region: str) -> str:
    """根据区服返回 ADB 基础路径（浏览器起始目录）"""
    return ADB_BASE_PATHS.get(server_region, "")


def get_adb_package_name(server_region: str) -> str:
    """根据区服返回包名（用于缓存路径映射）"""
    if server_region == "japan":
        return "com.Yostar JP.BlueArchive"
    return "com.nexon.bluearchive"
