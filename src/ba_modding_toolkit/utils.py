# utils.py

import binascii
from PIL import Image
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .i18n import i18n_manager, t

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

def get_BA_path(region: str = "global") -> str | None:
    """获取游戏安装路径，带缓存机制
    
    Args:
        region: 区服，"global" 或 "japan"
    
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
    else:
        result = None

    _ba_path_cache[region] = result
    return result

def get_version() -> str:
    """从 pyproject.toml 读取版本号"""
    try:
        from ba_modding_toolkit._version import __version__
        print(__version__)
    except ImportError:
        # 如果在本地开发环境没有这个文件，回退到读取 pyproject.toml
        try:
            import toml
            with open("pyproject.toml", 'r', encoding='utf-8') as f:
                data = toml.load(f)
                __version__ = data["project"]["version"] + "-dev"
        except:
            __version__ = "0.0.0-dev"
    return __version__

def no_log(message):
    """A dummy logger that does nothing."""
    pass


def parse_hex_bytes(hex_str: str | None) -> bytes | None:
    """将字符串转换为 bytes

    Args:
        hex_str: 如果以 0x 或 0X 开头，则按十六进制解析（如 "0x08080808"）
               否则按 ASCII 字符串直接编码

    Returns:
        如果输入为空或无效则返回 None，否则返回对应的 bytes
    """
    if not hex_str:
        return None
    try:
        # 如果以 0x 或 0X 开头，按十六进制解析
        if hex_str.startswith("0x") or hex_str.startswith("0X"):
            hex_str = hex_str[2:]
            # 验证是否为有效的十六进制字符串（必须为偶数长度）
            if len(hex_str) % 2 != 0:
                return None
            return bytes.fromhex(hex_str)
        # 否则按 ASCII 字符串直接编码
        return hex_str.encode("ascii")
    except (ValueError, UnicodeEncodeError):
        return None


LogFunc = Callable[[str], None]

class CRCUtils:
    """
    一个封装了CRC32计算和修正逻辑的工具类。
    Prototype by [kalina](https://github.com/kalinaowo)
    """

    POLY_NORMAL = 0x104C11DB7
    POLY_DEGREE = 32
    GF2_INVERSE_X32 = 0xCBF1ACDA
    _BIT_REVERSE_TABLE = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))

    # --- 公开的静态方法 ---

    @staticmethod
    def compute_crc32(src: Path | str | bytes) -> int:
        """
        计算数据的标准CRC32 (IEEE)值。
        """
        if isinstance(src, bytes):
            return binascii.crc32(src) & 0xFFFFFFFF
        return CRCUtils._compute_crc32_file(src)

    @staticmethod
    def _compute_crc32_file(path: str | Path) -> int:
        """分块计算文件 CRC32，避免大文件内存溢出"""
        crc = 0
        with open(path, "rb") as f:
            while chunk := f.read(8192):  # 8KB 分块
                crc = binascii.crc32(chunk, crc)
        return crc & 0xFFFFFFFF

    @staticmethod
    def check_crc_match(source_1: Path | str | bytes, source_2: Path | str | bytes) -> tuple[bool, int, int]:
        """
        检测两个文件或字节数据的CRC值是否匹配。
        返回 (是否匹配, crc_1, crc_2)。
        """
        crc_1 = CRCUtils.compute_crc32(source_1)
        crc_2 = CRCUtils.compute_crc32(source_2)
        
        return crc_1 == crc_2, crc_1, crc_2
    
    @staticmethod
    def apply_crc_fix(modified_data: bytes, target_crc: int) -> bytes | None:
        """
        计算修正CRC后的数据，使其达到指定的目标CRC值。
        如果修正成功，返回修正后的完整字节数据；如果失败，返回None。
        """
        # 计算新数据加上4个空字节的CRC，为修正值留出空间
        base_crc = binascii.crc32(modified_data)
        crc_with_zeros = binascii.crc32(b'\x00\x00\x00\x00', base_crc) & 0xFFFFFFFF
        k = CRCUtils._reverse_bits_32(target_crc ^ crc_with_zeros)

        correction_value = CRCUtils._gf2_multiply_mod(k, CRCUtils.GF2_INVERSE_X32)
        correction_bytes = CRCUtils._reverse_bytes_internal_bits(correction_value)
        final_data = modified_data + correction_bytes

        final_crc = CRCUtils.compute_crc32(final_data)
        is_crc_match = (final_crc == target_crc)
        return final_data if is_crc_match else None

    @staticmethod
    def manipulate_file_crc(modified_path: str | Path, target_crc: int, extra_bytes: bytes | None = None) -> bool:
        """
        修正modified_path文件的CRC，使其达到指定的目标CRC值
        这个函数会直接修改文件内容，而不是输出到指定目录
        extra_bytes: 可选的4字节数据，将在CRC计算前附加到modified_data后
        """
        with open(str(modified_path), "rb") as f:
            modified_data = f.read()

        if extra_bytes:
            modified_data = modified_data + extra_bytes

        corrected_data = CRCUtils.apply_crc_fix(modified_data, target_crc)

        if corrected_data:
            with open(modified_path, "wb") as f:
                f.write(corrected_data)
            return True

        return False

    # --- 内部使用的私有静态方法 ---

    @staticmethod
    def _reverse_bits_32(val_u32: int) -> int:
        """快速翻转 32 位整数的所有比特位"""
        b = val_u32.to_bytes(4, 'big')
        rev_b = bytes(CRCUtils._BIT_REVERSE_TABLE[x] for x in b[::-1])
        return int.from_bytes(rev_b, 'big')

    @staticmethod
    def _reverse_bytes_internal_bits(val_u32: int) -> bytes:
        """将整数转为字节，并反转每个字节内部的比特位"""
        b = val_u32.to_bytes(4, 'big')
        return bytes(CRCUtils._BIT_REVERSE_TABLE[x] for x in b)

    @staticmethod
    def _gf2_multiply_mod(a, b):
        result = 0
        while b != 0:
            if b & 1:
                result ^= a
            b >>= 1
            a <<= 1
            if a >> CRCUtils.POLY_DEGREE:
                a ^= CRCUtils.POLY_NORMAL
        return result

def get_environment_info(ignore_tk: bool = False):
    """Collects and formats key environment details."""
    
    # --- Attempt to import libraries and get their versions ---
    # This approach prevents the script from crashing if a library is not installed.
    import importlib.metadata
    
    try:
        import UnityPy
        unitypy_version = UnityPy.__version__ or "Installed"
    except ImportError:
        unitypy_version = "Not installed"

    try:
        from PIL import Image
        pillow_version = Image.__version__ or "Installed"
    except ImportError:
        pillow_version = "Not installed"

    try:
        if not ignore_tk:
            import tkinter
            tk_version = tkinter.Tcl().eval('info patchlevel') or "Installed"
        else:
            tk_version = "Ignored"
    except ImportError:
        tk_version = "Not installed"
    except tkinter.TclError:
        tk_version = "Unknown"

    try:
        if not ignore_tk:
            import tkinterdnd2
            tkinterdnd2_version = tkinterdnd2.TkinterDnD.TkdndVersion or "Installed"
        else:
            tkinterdnd2_version = "Ignored"
    except ImportError:
        tkinterdnd2_version = "Not installed"
    except AttributeError:
        tkinterdnd2_version = "Unknown"

    try:
        if not ignore_tk:
            tb_version = importlib.metadata.version('ttkbootstrap')
        else:
            tb_version = "Ignored"
    except ImportError:
        tb_version = "Not installed"
    except (AttributeError, importlib.metadata.PackageNotFoundError):
        tb_version = "Unknown"

    try:
        import toml
        toml_version = toml.__version__ or "Installed"
    except ImportError:
        toml_version = "Not installed"

    try:
        import SpineAtlas
        spineatlas_version = SpineAtlas.__version__ or "Installed"
    except ImportError:
        spineatlas_version = "Not installed"
    except AttributeError:
        try:
            spineatlas_version = importlib.metadata.version('spineatlas')
        except (ImportError, importlib.metadata.PackageNotFoundError):
            spineatlas_version = "Unknown"

    # --- Locale and Encoding Information (crucial for file path/text bugs) ---
    try:
        import locale
        lang_code, encoding = locale.getdefaultlocale()
        system_locale = f"{lang_code} (Encoding: {encoding})"
    except (ValueError, TypeError):
        system_locale = "Could not determine"

    try:
        version = get_version()
    except Exception as e:
        print(e)
        version = "Unknown"

    import platform
    import sys

    def _is_admin():
        if sys.platform == 'win32':
            try:
                import ctypes
                return ctypes.windll.shell32.IsUserAnAdmin() != 0
            except (ImportError, AttributeError):
                return False
        return False # 在非Windows系统上不是管理员

    def _exe_dir() -> str | None:
        if "__compiled__" in globals() and hasattr(__compiled__, "containing_dir"):
            return str(Path(__compiled__.containing_dir).resolve())
        return None

    lines: list[str] = []
    lines.append("======== Environment Information ========")

    # --- Available Languages ---
    lines.append("\n--- BA Modding Toolkit ---")
    lines.append(f"Version:             {version}")
    lines.append(f"Current Language:    {i18n_manager.lang}")
    lines.append(f"Available Languages: {', '.join(i18n_manager.get_available_languages())}")

    # --- System Information ---
    lines.append("\n--- System Information ---")
    lines.append(f"Operating System:    {platform.system()} {platform.release()} ({platform.architecture()[0]})")
    lines.append(f"System Platform:     {sys.platform}")
    lines.append(f"System Locale:       {system_locale}")
    lines.append(f"Filesystem Enc:      {sys.getfilesystemencoding()}")
    lines.append(f"Preferred Enc:       {locale.getpreferredencoding()}")
    
    # --- Python Information ---
    lines.append("\n--- Python Information ---")
    lines.append(f"Python Version:      {sys.version.splitlines()[0]}")
    lines.append(f"Python Executable:   {sys.executable}")
    lines.append(f"Working Directory:   {Path.cwd()}")
    lines.append(f"EXE Directory:       {_exe_dir() or 'N/A'}")
    lines.append(f"Running as Admin:    {_is_admin()}")

    # --- Library Versions ---
    lines.append("\n--- Library Versions ---")
    lines.append(f"UnityPy Version:     {unitypy_version}")
    lines.append(f"Pillow Version:      {pillow_version}")
    lines.append(f"Tkinter Version:     {tk_version}")
    lines.append(f"TkinterDnD2 Version: {tkinterdnd2_version}")
    lines.append(f"ttkbootstrap Version:{tb_version}")
    lines.append(f"toml Version:        {toml_version}")
    lines.append(f"SpineAtlas Version:  {spineatlas_version}")
    
    lines.append("")

    return "\n".join(lines)

class ImageUtils:
    @staticmethod
    def bleed_image(image: Image.Image, iteration: int = 8) -> Image.Image:
        """
        对图像进行 Bleed 处理。
        """
        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        width, height = image.size
        original_alpha = image.getchannel('A')
        
        # 优化：使用 LUT 代替逐像素操作
        lut = [255] * 256
        lut[0] = 0
        mask = original_alpha.point(lut)

        # 优化：如果没有完全透明像素，直接返回
        if original_alpha.getextrema()[0] > 0:
            return image

        current_canvas = image.copy()
        
        for _ in range(iteration):
            layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            offsets = [(1, 0), (-1, 0), (0, 1), (0, -1)]
            
            for dx, dy in offsets:
                shifted = current_canvas.transform(
                    (width, height),
                    Image.Transform.AFFINE,
                    (1, 0, -dx, 0, 1, -dy)
                )
                layer.alpha_composite(shifted)
            
            layer.alpha_composite(current_canvas)
            current_canvas = layer

        result = Image.composite(image, current_canvas, mask)
        r, g, b, _ = result.split()
        final = Image.merge("RGBA", (r, g, b, original_alpha))

        return final
