# gui/tabs/jp_conversion_tab.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path
from enum import IntEnum

from ...i18n import t
from ... import core
from ...searching import get_search_dirs, find_target_bundles, search_prefix
from ..base_tab import TabFrame
from ..components import DropZone, ModeSwitcher, SettingRow, UIComponents
from ..windows import FileSelectionDialog
from ..utils import confirm_and_replace

class Mode(IntEnum):
    """日服/国际服转换模式"""
    MODERN_TO_LEGACY = 0
    LEGACY_TO_MODERN = 1


class LegacyConversionTab(TabFrame):
    """旧版与新版格式互相转换的标签页"""

    def __init__(self, *args, **kwargs):
        self.current_file_pairs: list[tuple[Path, Path]] = []
        super().__init__(*args, **kwargs)

    def create_widgets(self):
        # --- 转换模式选择 ---
        self.mode_var = tk.IntVar(value=Mode.LEGACY_TO_MODERN)

        self.mode_switcher = ModeSwitcher(
            self,
            self.mode_var,
            [
                (Mode.LEGACY_TO_MODERN, t("ui.legacy_conversion.mode_legacy_to_modern")),
                (Mode.MODERN_TO_LEGACY, t("ui.legacy_conversion.mode_modern_to_legacy")),
            ],
            command=self._switch_view
        )

        # 创建转换模式的UI
        self._create_convert_mode_widgets()

        # 根据选择的模式更新UI标签文案"""
        self._switch_view()
    
    def _switch_view(self):
        """根据选择的模式更新UI标签文案"""
        if self.mode_var.get() == Mode.MODERN_TO_LEGACY:
            self.legacy_zone.config(text=t("ui.legacy_conversion.role_legacy_target"))
            self.modern_zone.config(text=t("ui.legacy_conversion.role_modern_source"))
        else:
            self.legacy_zone.config(text=t("ui.legacy_conversion.role_legacy_source"))
            self.modern_zone.config(text=t("ui.legacy_conversion.role_modern_target"))

    # --- 转换模式UI ---
    def _create_convert_mode_widgets(self):
        # 文件输入区域
        file_frame = tb.Frame(self)
        file_frame.pack(fill=tk.BOTH, pady=(0, 3))
        
        # 1. 国际服 Bundle 文件
        self.legacy_zone = DropZone(
            file_frame,
            title=t("ui.legacy_conversion.role_legacy_source"),
            placeholder_text=t("ui.legacy_conversion.placeholder_legacy_bundle"),
            on_files_selected=self.on_legacy_selected,
            filetypes=[(t("file_type.bundle"), "*.bundle"), (t("file_type.all_files"), "*.*")],
            allow_multiple=False,
            logger=self.logger
        )
        self.legacy_zone.pack(fill=tk.X, pady=(0, 3))

        # 2. 日服 Bundle 文件列表
        self.modern_zone = DropZone(
            file_frame,
            title=t("ui.legacy_conversion.role_modern_source"),
            placeholder_text=t("ui.legacy_conversion.placeholder_modern_bundles"),
            on_files_selected=self._on_modern_files_selected,
            filetypes=[(t("file_type.bundle"), "*.bundle"), (t("file_type.all_files"), "*.*")],
            allow_multiple=True,
            logger=self.logger
        )
        
        # --- 选项设置区域 ---
        options_frame = tb.Labelframe(self, text=t("ui.label.options"), padding=10)
        options_frame.pack(fill=tk.X)
        
        # --- 操作按钮 ---
        action_button_frame = tb.Frame(self)
        action_button_frame.pack(fill=tk.X, pady=10)
        action_button_frame.grid_columnconfigure((0, 1), weight=1)
        
        self.run_button = UIComponents.create_button(
            action_button_frame, t("action.convert"),
            self.run_conversion_thread,
            bootstyle="success",
            style="large"
        )
        self.run_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        self.replace_button = UIComponents.create_button(
            action_button_frame, t("action.replace_original"),
            self.replace_original_thread,
            bootstyle="danger",
            state="disabled",
            style="large"
        )
        self.replace_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def on_legacy_selected(self, path: Path):
        """旧版文件选中后的处理"""
        self.logger.log(t("log.file.loaded", path=path))
        self.logger.status(t("status.ready"))
        # 自动搜索新版文件
        self._auto_find_modern_files()

    # --- 自动搜索逻辑 ---
    def _auto_find_modern_files(self):
        """当指定了旧版文件后，自动在资源目录查找所有匹配的文件"""
        # 清除旧的文件列表，准备重新搜索
        self.modern_zone.clear()
        self.run_in_thread(self._find_worker)

    def _find_worker(self):
        self.logger.status(t("status.searching"))
        base_game_dir = Path(self.app.game_resource_dir_var.get())
        game_search_dirs = get_search_dirs(base_game_dir)

        # 搜索日服文件
        modern_files, _ = search_prefix(
            self.legacy_zone.path, game_search_dirs, self.logger.log
        )

        if modern_files:
            self.master.after(0, lambda: self._update_modern_listbox(modern_files))
            self.logger.status(t("status.ready"))
        else:
            self.logger.log(f'⚠️ {t("log.search.no_found")}')
            self.logger.status(t("status.search_not_found"))

    def _update_modern_listbox(self, files: list[Path]):
        self.modern_zone.clear()
        self.modern_zone.set_files(files)
        self.logger.log(t("log.search.found_count", count=len(files)))

    # --- 新版文件添加后自动查找旧版文件 ---
    def _on_modern_files_selected(self, paths: list[Path]) -> None:
        """当文件被选中时的回调，如果是第一个文件则查找对应的旧版文件"""
        if not paths:
            return
        # 只有当旧版文件未设置时才进行查找
        if self.legacy_zone.path is not None:
            return
        # 使用第一个文件作为查找基础
        first_file = paths[0]
        self._auto_find_legacy_file(first_file)

    def _auto_find_legacy_file(self, reference_file: Path):
        """当指定了参考文件后，自动在资源目录查找对应的旧版文件"""
        self.run_in_thread(lambda: self._find_legacy_worker(reference_file))

    def _find_legacy_worker(self, reference_file: Path):
        """后台线程：查找旧版文件"""
        self.logger.status(t("status.searching"))

        # 更新UI为搜索中状态
        self.master.after(0, lambda: self.legacy_zone.set_searching())

        base_game_dir = Path(self.app.game_resource_dir_var.get())
        search_paths = get_search_dirs(base_game_dir)

        # 使用find_target_bundles查找旧版文件
        found_paths, message = find_target_bundles(
            [reference_file],
            search_paths,
            self.logger.log
        )

        # 在主线程中处理结果
        self.master.after(0, lambda: self._handle_legacy_search_result(found_paths, message))

    def _handle_legacy_search_result(self, found_paths: list[Path], message: str):
        """处理旧版文件搜索结果"""
        if not found_paths:
            # 没有找到匹配文件
            ui_message = t("ui.mod_update.status_not_found", message=message)
            self.legacy_zone.set_error(ui_message)
            self.logger.status(t("status.search_not_found"))
        elif len(found_paths) == 1:
            self.legacy_zone.set_files(found_paths)
            self.logger.log(t("log.file.loaded", path=found_paths[0]))
            self.logger.status(t("status.ready"))
        else:
            # 多个匹配文件，弹出选择对话框
            dialog = FileSelectionDialog(
                self.master,
                title=t("ui.dialog.select_file"),
                candidates=found_paths,
                message=t("ui.dialog.multiple_matches_found", count=len(found_paths)),
                display_formatter=lambda p: f"{p.parent.name} / {p.name}"
            )

            selected_path = dialog.get_selected_path()
            if selected_path:
                self.legacy_zone.set_files(selected_path)
                self.logger.log(t("log.file.loaded", path=selected_path))
                self.logger.status(t("status.ready"))
            else:
                # 用户取消了选择
                ui_message = t("ui.mod_update.status_not_found", message=t("ui.dialog.selection_cancelled"))
                self.legacy_zone.set_warning(ui_message)
                self.logger.status(t("status.search_not_found"))

    # --- 核心转换流程 ---
    def run_conversion_thread(self):
        self.run_in_thread(self.run_conversion)
    
    # --- 覆盖原文件功能 ---
    def replace_original_thread(self):
        """覆盖原文件的线程入口"""
        confirm_and_replace(
            file_pairs=self.current_file_pairs,
            create_backup=self.app.create_backup_var.get(),
            log=self.logger.log,
            button_to_disable=self.replace_button,
            master=self.master,
        )

    def run_conversion(self):
        # 1. 验证输入
        output_dir = Path(self.app.output_dir_var.get())
        modern_files = self.modern_zone.paths

        if not self.legacy_zone.path:
            messagebox.showerror(t("common.error"), t("message.no_file_selected"))
            return
        if not modern_files:
            messagebox.showerror(t("common.error"), t("message.list_empty"))
            return

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.logger.log(f'❌ {t("message.create_dir_failed_detail",path=output_dir, error=e)}')
            return
        
        # 重置输出文件路径列表和按钮状态
        self.current_file_pairs = []
        self.master.after(0, lambda: self.replace_button.config(state=tk.DISABLED))
        
        # 2. 准备选项
        target_bundle = self.legacy_zone.path if self.mode_var.get() == Mode.MODERN_TO_LEGACY else modern_files[0]
        perform_crc = self.app.resolve_crc_setting(target_bundle)
        
        save_options = self.app.build_save_options(perform_crc)
        
        # 从设置页获取资源类型
        asset_types_to_replace = self.app.get_asset_types()
        
        # 3. 调用处理函数
        self.logger.status(t("common.processing"))
        if self.mode_var.get() == Mode.MODERN_TO_LEGACY:
            success, message, file_pair = core.process_modern_to_legacy_conversion(
                legacy_bundle_path=self.legacy_zone.path,
                modern_bundle_paths=modern_files,
                output_dir=output_dir,
                save_options=save_options,
                asset_types_to_replace=asset_types_to_replace,
                log=self.logger.log
            )

            if success and file_pair:
                self.current_file_pairs = [file_pair]
                self.master.after(0, lambda: self.replace_button.config(state=tk.NORMAL))
        else:  # LEGACY_TO_MODERN
            success, message, file_pairs = core.process_legacy_to_modern_conversion(
                legacy_bundle_path=self.legacy_zone.path,
                modern_bundle_paths=modern_files,
                output_dir=output_dir,
                save_options=save_options,
                asset_types_to_replace=asset_types_to_replace,
                log=self.logger.log,
                skip_unchanged=True
            )

            if success and file_pairs:
                self.current_file_pairs = file_pairs
                self.master.after(0, lambda: self.replace_button.config(state=tk.NORMAL))
        
        # 4. 结果反馈
        if success:
            self.logger.status(t("status.done"))
            messagebox.showinfo(t("common.success"), message)
        else:
            self.logger.status(t("status.failed"))
            messagebox.showerror(t("common.fail"), message)
    