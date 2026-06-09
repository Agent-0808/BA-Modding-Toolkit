# gui/utils.py

import sys
import subprocess
import os
import tkinter as tk
from tkinter import messagebox, filedialog
from pathlib import Path
import shutil
from typing import Callable, TYPE_CHECKING
import ttkbootstrap as tb

from ..utils import no_log
from ..i18n import t
from ..models import FilePair, FileType

from tkinterdnd2.TkinterDnD import DnDWrapper, _require
from ttkbootstrap.window import Window as tbWindow

class tbDnDWindow(tbWindow, DnDWrapper):
    """结合 ttkbootstrap.Window 与 TkinterDnD 拖放功能的窗口类"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = _require(self)

# --- 文件类型映射表 ---
FILE_TYPE_MAP: dict[FileType, tuple[str, str]] = {
    # 类型 -> (语言键, glob模式)
    FileType.BUNDLE: ("file_type.bundle", "*.bundle"),
    FileType.BUNDLE_BACKUP: ("file_type.bundle_backup", "*.bundle.backup"),
    FileType.ALL: ("file_type.all_files", "*.*"),
    FileType.EXECUTABLE: ("file_type.executable", "*.exe"),
}


def build_filetypes(file_types: list[FileType | str]) -> list[tuple[str, str]]:
    """根据文件类型列表构造 filetypes tuple 列表"""
    result = []
    for type in file_types:
        if type in FILE_TYPE_MAP:
            lang_key, pattern = FILE_TYPE_MAP[type]
            result.append((t(lang_key), pattern))
        else:
            # 未知类型，直接使用扩展名
            result.append((type, f"*{type}"))
    return result

def is_multiple_drop(data: str) -> bool:
    """
    检查拖放事件的数据是否包含多个文件路径。
    多个文件的 event.data 通常是 '{path1} {path2}' 的形式。
    """
    return '} {' in data

def handle_drop(event: tk.Event, 
                callback: Callable[[Path], None],
                allow_multiple: bool = False,
                error_title: str = None,
                error_message: str = None,
                validation_callback: Callable[[Path], bool] | None = None) -> bool:
    """
    通用的拖放事件处理函数
    
    Args:
        event: 拖放事件对象
        callback: 处理单个文件路径的回调函数，接收Path对象
        allow_multiple: 是否允许多个文件，默认为False
        error_title: 错误提示标题，默认为"message.invalid_operation"
        error_message: 错误提示消息，默认为"message.drop_single_file"
        validation_callback: 自定义验证函数，接收Path对象，返回bool表示是否有效
    
    Returns:
        是否成功处理（False表示因多文件限制或验证失败而未处理）
    """
    if is_multiple_drop(event.data):
        if not allow_multiple:
            messagebox.showwarning(
                error_title or t("message.invalid_operation"), 
                error_message or t("message.drop_single_file")
            )
            return False
        else:
            paths = [Path(p) for p in event.widget.tk.splitlist(event.data)]
            for path in paths:
                if validation_callback and not validation_callback(path):
                    return False
                callback(path)
            return True
    
    path = Path(event.data.strip('{}'))
    if validation_callback and not validation_callback(path):
        return False
    callback(path)
    return True

def open_directory(path: str | Path, log = no_log, create_if_not_exist: bool = False) -> None:
    """
    打开文件资源管理器。
    
    Args:
        path: 要打开的目录路径
        log: 日志函数，用于记录操作
        create_if_not_exist: 如果目录不存在，是否提示创建
    """
    
    try:
        path_obj = Path(path).resolve()
        if not path_obj.is_dir():
            if create_if_not_exist:
                if messagebox.askyesno(t("common.tip"), t("message.dir_not_found_create", path=path_obj)):
                    path_obj.mkdir(parents=True, exist_ok=True)
                else: 
                    return
            else:
                messagebox.showwarning(t("common.warning"), t("message.path_invalid", path=path_obj))
                return
        
        # 检测是否为 WSL 环境
        is_wsl = False
        if sys.platform == 'linux':
            try:
                with open('/proc/version', 'r') as f:
                    if 'microsoft' in f.read().lower():
                        is_wsl = True
            except Exception:
                pass

        # --- 打开目录 ---
        if sys.platform == 'win32':
            os.startfile(str(path_obj))
            
        elif is_wsl:
            # WSL 环境：先转换路径，再调用 Explorer
            try:
                # 使用 wslpath -w 将 Linux 路径转换为 Windows 路径
                result = subprocess.run(
                    ['wslpath', '-w', str(path_obj)], 
                    capture_output=True, text=True, check=True
                )
                windows_path = result.stdout.strip()

                subprocess.run(['explorer.exe', windows_path])
                path_obj = Path(windows_path)  # 更新路径为Windows路径
                
            except subprocess.CalledProcessError as e:
                log(t("log.process_failed", error=e))
                messagebox.showerror(t("common.error"), t("message.cannot_open_explorer", error=e))
                return
            
        else:
            # Linux/macOS
            try:
                if sys.platform == 'darwin':  # macOS
                    subprocess.run(['open', str(path_obj)], check=True)
                else:  # Linux
                    subprocess.run(['xdg-open', str(path_obj)], check=True)
                
            except (subprocess.CalledProcessError, FileNotFoundError):
                messagebox.showinfo(t("common.tip"), t("message.open_manually", path=path_obj))
                return
        
        # 统一记录成功打开目录的日志
        log(t("log.file.directory_opened", path=path_obj))
                
    except Exception as e:
        messagebox.showerror(t("common.error"), t("message.process_failed", error=e))

def _perform_file_replace(
    source_path: Path,
    dest_path: Path,
    create_backup: bool = True,
    log = no_log
) -> bool:
    """
    执行实际的文件替换操作（纯替换/备份逻辑，无UI交互）
    """
    if not source_path or not source_path.exists():
        return False
    if not dest_path or not dest_path.exists():
        return False
    if source_path == dest_path:
        return False

    try:
        if create_backup:
            backup_path = dest_path.with_suffix(dest_path.suffix + '.backup')
            try:
                shutil.copy2(dest_path, backup_path)
            except Exception as e:
                log(t("log.file.backup_failed", error=e))
                return False
            log(t("log.file.backed_up", path=backup_path))

        log(t("log.file.overwritten", path=dest_path))
        shutil.copy2(source_path, dest_path)
        return True

    except Exception as e:
        log(t("log.process_failed", error=e))
        return False


def replace_file(
    source_path: Path,
    dest_path: Path,
    create_backup: bool = True,
    ask_confirm: bool = True,
    confirm_message: str = "",
    log = no_log,
) -> bool:
    """
    安全地替换文件，包含确认、备份和日志记录功能。
    返回操作是否成功。
    """
    if not source_path or not source_path.exists():
        messagebox.showerror(t("common.error"), t("message.file_not_found", path=source_path))
        return False
    if not dest_path or not dest_path.exists():
        messagebox.showerror(t("common.error"), t("message.file_not_found", path=dest_path))
        return False
    if source_path == dest_path:
        messagebox.showerror(t("common.error"), t("message.same_file"))
        return False

    if ask_confirm and not messagebox.askyesno(t("common.warning"), confirm_message):
        return False

    success = _perform_file_replace(source_path, dest_path, create_backup, log)

    if success:
        log(t("status.done"))
        messagebox.showinfo(t("common.success"), t("message.process_success"))
        return True
    else:
        messagebox.showerror(t("common.error"), t("message.process_failed", error=""))
        return False


def replace_files(
    file_pairs: list[FilePair],
    create_backup: bool = True,
    ask_confirm: bool = True,
    confirm_message: str = "",
    log = no_log,
) -> tuple[int, int]:
    """
    批量替换文件，包含确认、备份和日志记录功能。

    Args:
        file_pairs: 文件对列表，每个元素为 (源文件路径, 目标文件路径) 的元组
        create_backup: 是否创建备份
        ask_confirm: 是否显示确认对话框
        confirm_message: 确认对话框的消息
        log: 日志函数

    Returns:
        tuple[int, int]: (成功数量, 失败数量) 的元组
    """

    # 显示确认对话框
    if ask_confirm and confirm_message:
        if not messagebox.askyesno(t("common.warning"), confirm_message):
            return -1, -1

    # 执行批量替换
    success_count = 0
    fail_count = 0

    for pair in file_pairs:
        success = _perform_file_replace(pair.output, pair.source, create_backup, log)
        if success:
            success_count += 1
        else:
            fail_count += 1

    # 显示结果
    log(t("log.success_fail", success=success_count, fail=fail_count))
    messagebox.showinfo(
        t("common.tip"),
        t("message.replace_result", success=success_count, fail=fail_count)
    )

    return success_count, fail_count 

def confirm_and_replace(
    file_pairs: list[FilePair],
    create_backup: bool,
    log,
    button_to_disable: tb.Button | None = None,
    master: tk.Tk | tk.Frame | None = None,
) -> bool:
    """
    统一的确认+替换流程，包含：
    1. 空检查
    2. 文件存在检查
    3. 确认对话框构建（含截断逻辑）
    4. 单/多文件分发
    5. 按钮状态管理

    Args:
        file_pairs: 文件对列表，每个元素为 (源文件路径, 目标文件路径) 的元组
        create_backup: 是否创建备份
        log: 日志函数
        button_to_disable: 操作完成后需要禁用的按钮（可选）
        master: tkinter master 对象，用于调度 UI 更新（可选）

    Returns:
        bool: 是否成功执行替换操作
    """
    if not file_pairs:
        messagebox.showerror(t("common.error"), t("message.no_file_selected"))
        return False

    for pair in file_pairs:
        if not pair.output.exists():
            messagebox.showerror(t("common.error"), t("message.file_not_found", path=pair.output))
            return False

    files_to_replace = [f"  {pair.source.name}" for pair in file_pairs[:10]]
    max_display = 10
    if len(file_pairs) > max_display:
        remaining_count = len(file_pairs) - max_display
        files_list = "\n".join(files_to_replace) + f"\n{t('message.and_more_files', count=remaining_count)}"
    else:
        files_list = "\n".join(files_to_replace)

    confirm_message = t("message.confirm_replace_files", count=len(file_pairs), files=files_list)

    if not messagebox.askyesno(t("common.warning"), confirm_message):
        return False

    if len(file_pairs) == 1:
        pair = file_pairs[0]
        replace_file(
            source_path=pair.output,
            dest_path=pair.source,
            create_backup=create_backup,
            ask_confirm=False,
            log=log,
        )
    else:
        replace_files(
            file_pairs=file_pairs,
            create_backup=create_backup,
            ask_confirm=False,
            log=log,
        )

    log(t("status.done"))

    if button_to_disable and master:
        master.after(0, lambda: button_to_disable.config(state=tk.DISABLED))

    return True

def select_directory(var: tk.Variable = None, title="", log=no_log):
    """
    选择目录并更新变量或返回路径
    
    Args:
        var: tkinter变量，用于存储选择的目录路径，如果为None则直接返回路径
        title: 目录选择对话框的标题
        log: 日志函数，用于记录操作
        
    Returns:
        如果var为None，返回选择的目录路径字符串，否则返回None
    """
    try:
        initial_dir = str(Path.home())
        if var is not None:
            current_path = Path(var.get())
            if current_path.is_dir(): 
                initial_dir = str(current_path)
                
        selected_dir = filedialog.askdirectory(title=title, initialdir=initial_dir)
        if selected_dir:
            if var is not None:
                var.set(str(Path(selected_dir)))
                log(t("log.file.loaded", path=selected_dir))
                return None
            else:
                log(t("log.file.loaded", path=selected_dir))
                return selected_dir
        return None
    except Exception as e:
        messagebox.showerror(t("common.error"), t("message.process_failed", error=e))
        return None

def select_file(title: str, 
                file_types: list[FileType | str] | list[tuple[str, str]] | None = None, 
                multiple: bool = False,
                callback: Callable[[Path | list[Path]], None] | None = None,
                log = no_log) -> Path | list[Path] | None:
    """
    统一的文件选择对话框函数
    
    Args:
        title: 对话框标题
        file_types: 文件类型过滤器，支持 FileType 列表或 tkinter tuple 格式
        multiple: 是否支持多选
        callback: 选择文件后的回调函数，接收Path或Path列表作为参数
        log: 日志函数，用于记录操作
        
    Returns:
        单选时返回Path或None，多选时返回Path列表或空列表
    """
    try:
        # 转换 file_types 为 tkinter 需要的格式
        if file_types is None:
            tk_filetypes = [(t("file_type.all_files"), "*.*")]
        elif file_types and isinstance(file_types[0], (FileType, str)):
            # FileType 列表，需要转换
            tk_filetypes = build_filetypes(file_types)
        else:
            # 已经是 tuple 格式，直接使用
            tk_filetypes = file_types
            
        if multiple:
            filepaths = filedialog.askopenfilenames(title=title, filetypes=tk_filetypes)
            if filepaths:
                paths = [Path(p) for p in filepaths]
                log(t("log.file.loaded", path=f"{len(paths)} files"))
                if callback:
                    callback(paths)
                return paths
            return []
        else:
            filepath = filedialog.askopenfilename(title=title, filetypes=tk_filetypes)
            if filepath:
                path = Path(filepath)
                log(t("log.file.loaded", path=path))
                if callback:
                    callback(path)
                return path
            return None
    except Exception as e:
        messagebox.showerror(t("common.error"), t("message.process_failed", error=e))
        return [] if multiple else None