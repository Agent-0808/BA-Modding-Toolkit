# utils/about.py
"""程序自身信息：版本元数据与环境诊断报告"""

from pathlib import Path

from .paths import EXE_DIR


def get_version_info() -> dict[str, str]:
    """获取版本信息（包含 commit、branch、build time 等元数据）"""
    info = {
        "version": "",
        "commit_hash": "",
        "commit_hash_short": "",
        "branch": "",
        "tag": "",
        "build_time": ""
    }
    try:
        from ba_modding_toolkit._version import (
            __version__, __commit_hash__, __commit_hash_short__,
            __branch__, __tag__, __build_time__
        )
        info["version"] = __version__
        info["commit_hash"] = __commit_hash__
        info["commit_hash_short"] = __commit_hash_short__
        info["branch"] = __branch__
        info["tag"] = __tag__
        info["build_time"] = __build_time__
    except ImportError:
        # 如果在本地开发环境没有这个文件，回退到读取 pyproject.toml
        try:
            import toml
            with open("pyproject.toml", 'r', encoding='utf-8') as f:
                data = toml.load(f)
                info["version"] = data["project"]["version"] + "-dev"
        except:
            pass

    return info


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

    import platform
    import sys
    from ..i18n import i18n_manager

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
            return str(EXE_DIR)
        return None

    lines: list[str] = []
    lines.append("======== Environment Information ========")

    # --- Available Languages ---
    lines.append("\n--- BA Modding Toolkit ---")
    version_info = get_version_info()
    lines.append(f"Version:             {version_info['version'] or 'N/A'}")
    lines.append(f"Commit:              {version_info['commit_hash'] or 'N/A'}")
    lines.append(f"Tag:                 {version_info['tag'] or 'N/A'}")
    lines.append(f"Build Time:          {version_info['build_time'] or 'N/A'}")
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
    lines.append(f"UnityPy:             {unitypy_version}")
    lines.append(f"Pillow:              {pillow_version}")
    lines.append(f"Tkinter:             {tk_version}")
    lines.append(f"TkinterDnD2:         {tkinterdnd2_version}")
    lines.append(f"ttkbootstrap:        {tb_version}")
    lines.append(f"toml:                {toml_version}")
    lines.append(f"SpineAtlas:          {spineatlas_version}")

    lines.append("")

    return "\n".join(lines)
