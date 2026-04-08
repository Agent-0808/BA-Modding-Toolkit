# gui/tabs/jp_conversion_tab.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path
from enum import IntEnum

from ...i18n import t
from ... import core
from ...utils import get_search_resource_dirs
from ..base_tab import TabFrame
from ..components import DropZone, FileListbox, ModeSwitcher, SettingRow, UIComponents
from ..dialogs import FileSelectionDialog
from ..utils import replace_file, replace_files

class Mode(IntEnum):
    """日服/国际服转换模式"""
    JP_TO_GLOBAL = 0
    GLOBAL_TO_JP = 1
    LEGACY_BATCH = 2

class JPGLConversionTab(TabFrame):
    """日服与国际服格式互相转换的标签页"""

    def __init__(self, *args, **kwargs):
        self.final_output_paths: list[Path] = []
        self.replaced_source_files: list[Path] = []  # 记录被成功替换的原始文件路径
        self.legacy_file_list: list[Path] = []  # 用于批量处理的旧版文件列表
        super().__init__(*args, **kwargs)

    def create_widgets(self):
        # --- 转换模式选择 ---
        self.mode_var = tk.IntVar(value=Mode.JP_TO_GLOBAL)

        self.mode_switcher = ModeSwitcher(
            self,
            self.mode_var,
            [
                (Mode.JP_TO_GLOBAL, t("ui.jp_conversion.mode_jp_to_gl")),
                (Mode.GLOBAL_TO_JP, t("ui.jp_conversion.mode_gl_to_jp")),
                (Mode.LEGACY_BATCH, t("ui.jp_conversion.mode_legacy_batch"))
            ],
            command=self._switch_view
        )

        # --- 容器框架 ---
        self.convert_frame = tb.Frame(self)  # JP_TO_GLOBAL 和 GLOBAL_TO_JP 模式
        self.batch_frame = tb.Frame(self)    # LEGACY_BATCH 模式
        
        # 创建两种模式的UI
        self._create_convert_mode_widgets(self.convert_frame)
        self._create_batch_mode_widgets(self.batch_frame)
        
        # 初始化视图
        self._switch_view()
    
    def _switch_view(self):
        """根据选择的模式显示或隐藏对应的UI框架"""
        if self.mode_var.get() == Mode.LEGACY_BATCH:
            self.convert_frame.pack_forget()
            self.batch_frame.pack(fill=tk.BOTH, expand=True)
        else:
            self.batch_frame.pack_forget()
            self.convert_frame.pack(fill=tk.BOTH, expand=True)
            # 更新转换模式的UI文案
            self._update_convert_mode_labels()

    def _update_convert_mode_labels(self):
        """根据当前转换模式更新标签文案"""
        if self.mode_var.get() == Mode.JP_TO_GLOBAL:
            self.global_zone.config(text=t("ui.jp_conversion.role_global_target"))
            self.jp_files_listbox.get_frame().config(text=t("ui.jp_conversion.role_jp_source"))
        else:  # GLOBAL_TO_JP
            self.global_zone.config(text=t("ui.jp_conversion.role_global_source"))
            self.jp_files_listbox.get_frame().config(text=t("ui.jp_conversion.role_jp_target"))

    # --- 转换模式UI (JP_TO_GLOBAL 和 GLOBAL_TO_JP) ---
    def _create_convert_mode_widgets(self, parent):
        # 文件输入区域
        file_frame = tb.Frame(parent)
        file_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 3))
        
        # 1. 国际服 Bundle 文件
        self.global_zone = DropZone(
            file_frame,
            title=t("ui.jp_conversion.role_global_source"),
            placeholder_text=t("ui.jp_conversion.placeholder_global_bundle"),
            on_file_selected=self.on_global_selected,
            filetypes=[(t("file_type.bundle"), "*.bundle"), (t("file_type.all_files"), "*.*")],
            logger=self.logger
        )
        self.global_zone.pack(fill=tk.X, pady=(0, 3))

        # 2. 日服 Bundle 文件列表
        self.jp_files_listbox = FileListbox(
            file_frame,
            title=t("ui.jp_conversion.role_jp_source"),
            placeholder_text=t("ui.jp_conversion.placeholder_jp_files"),
            height=3,
            logger=self.logger,
            on_files_added=self._on_jp_files_added
        )
        self.jp_files_listbox.get_frame().pack(fill=tk.BOTH, expand=True)
        
        # --- 选项设置区域 ---
        options_frame = tb.Labelframe(parent, text=t("ui.label.options"), padding=10)
        options_frame.pack(fill=tk.X)
        
        # 自动搜索开关
        SettingRow.create_switch(
            options_frame,
            label=t("option.auto_search"),
            variable=self.app.auto_search_var,
            tooltip=t("option.auto_search_info")
        )
        
        # --- 操作按钮 ---
        action_button_frame = tb.Frame(parent)
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

    # --- 批量模式UI (LEGACY_BATCH) ---
    def _create_batch_mode_widgets(self, parent):
        # 批量处理文件列表
        self.batch_file_listbox = FileListbox(
            parent,
            title=t("ui.label.mod_file"),
            file_list=self.legacy_file_list,
            placeholder_text=t("ui.mod_update.placeholder_batch"),
            height=10,
            logger=self.logger,
            display_formatter=lambda p: f"{p.parent.name} / {p.name}"
        )
        self.batch_file_listbox.get_frame().pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 操作按钮区域
        action_button_frame = tb.Frame(parent)
        action_button_frame.pack(fill=tk.X, pady=10)
        action_button_frame.grid_columnconfigure((0, 1), weight=1)
        
        # 运行按钮
        run_button = UIComponents.create_button(
            action_button_frame, 
            text=t("action.start"), 
            command=self.run_conversion_thread,
            bootstyle="success",
            style="large"
        )
        run_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        # 替换原文件按钮
        self.batch_replace_button = UIComponents.create_button(
            action_button_frame,
            text=t("action.replace_original"),
            command=self.replace_original_thread,
            bootstyle="danger",
            state="disabled",
            style="large"
        )
        self.batch_replace_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def on_global_selected(self, path: Path):
        """Global 文件选中后的处理"""
        self.logger.log(t("log.file.loaded", path=path))
        self.logger.status(t("status.ready"))
        # 自动搜索 JP 文件
        if self.app.auto_search_var.get():
            self._auto_find_jp_files()

    # --- 自动搜索逻辑 ---
    def _auto_find_jp_files(self):
        """当指定了 Global 文件后，自动在资源目录查找所有匹配的文件"""
        if not self.app.game_resource_dir_var.get():
            self.logger.log(f'⚠️ {t("log.jp_convert.auto_search_no_game_dir")}')
            return
        if not self.global_zone.path:
            self.logger.log(f'⚠️ {t("log.file.not_exist", path=self.global_zone.path)}')
            return
        
        # 清除旧的文件列表，准备重新搜索
        self.jp_files_listbox._clear_list()
        self.run_in_thread(self._find_worker)

    def _find_worker(self):
        self.logger.status(t("status.searching"))
        base_game_dir = Path(self.app.game_resource_dir_var.get())
        game_search_dirs = get_search_resource_dirs(base_game_dir, self.app.auto_detect_subdirs_var.get())

        if self.mode_var.get() == Mode.LEGACY_BATCH:
            # 搜索新版国际服文件
            new_global_files = core.find_all_jp_counterparts(
                self.global_zone.path, game_search_dirs, self.logger.log
            )
            
            if new_global_files:
                self.master.after(0, lambda: self._update_jp_listbox(new_global_files))
                self.logger.status(t("status.ready"))
            else:
                self.logger.log(f'⚠️ {t("log.search.no_found")}')
                self.logger.status(t("status.search_not_found"))
        else:
            # 搜索日服文件
            jp_files = core.find_all_jp_counterparts(
                self.global_zone.path, game_search_dirs, self.logger.log
            )
            
            if jp_files:
                self.master.after(0, lambda: self._update_jp_listbox(jp_files))
                self.logger.status(t("status.ready"))
            else:
                self.logger.log(f'⚠️ {t("log.search.no_found")}')
                self.logger.status(t("status.search_not_found"))

    def _update_jp_listbox(self, files: list[Path]):
        self.jp_files_listbox._clear_list()
        self.jp_files_listbox.add_files(files)
        self.logger.log(t("log.search.found_count", count=len(files)))

    # --- 反向查找：JP文件添加后自动查找Global文件 ---
    def _on_jp_files_added(self, paths: list[Path]) -> None:
        """当文件被添加时的回调，如果是第一个文件且开启了自动搜索，则查找对应的Global文件"""
        if not self.app.auto_search_var.get():
            return
        if not paths:
            return
        # 只有当Global文件未设置时才进行查找
        if self.global_zone.path is not None:
            return
        # 使用第一个文件作为查找基础
        first_file = paths[0]
        self._auto_find_global_file(first_file)

    def _auto_find_global_file(self, reference_file: Path):
        """当指定了参考文件后，自动在资源目录查找对应的Global文件"""
        if not self.app.game_resource_dir_var.get():
            self.logger.log(f'⚠️ {t("log.jp_convert.auto_search_no_game_dir")}')
            return

        self.run_in_thread(lambda: self._find_global_worker(reference_file))

    def _find_global_worker(self, reference_file: Path):
        """后台线程：查找Global文件"""
        self.logger.status(t("status.searching"))

        # 更新UI为搜索中状态
        self.master.after(0, lambda: self.global_zone.set_searching())

        base_game_dir = Path(self.app.game_resource_dir_var.get())
        search_paths = get_search_resource_dirs(base_game_dir, self.app.auto_detect_subdirs_var.get())

        # 使用find_new_bundle_path查找Global文件
        found_paths, message = core.find_new_bundle_path(
            reference_file,
            search_paths,
            self.logger.log
        )

        # 在主线程中处理结果
        self.master.after(0, lambda: self._handle_global_search_result(found_paths, message))

    def _handle_global_search_result(self, found_paths: list[Path], message: str):
        """处理Global文件搜索结果"""
        if not found_paths:
            # 没有找到匹配文件
            ui_message = t("ui.mod_update.status_not_found", message=message)
            self.global_zone.set_error(ui_message)
            self.logger.status(t("status.search_not_found"))
        elif len(found_paths) == 1:
            self.global_zone.set_path(found_paths[0])
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
                self.global_zone.set_path(selected_path)
                self.logger.log(t("log.file.loaded", path=selected_path))
                self.logger.status(t("status.ready"))
            else:
                # 用户取消了选择
                ui_message = t("ui.mod_update.status_not_found", message=t("ui.dialog.selection_cancelled"))
                self.global_zone.set_warning(ui_message)
                self.logger.status(t("status.search_not_found"))

    # --- 核心转换流程 ---
    def run_conversion_thread(self):
        self.run_in_thread(self.run_conversion)
    
    # --- 覆盖原文件功能 ---
    def replace_original_thread(self):
        """覆盖原文件的线程入口"""
        if not self.final_output_paths:
            messagebox.showerror(t("common.error"), t("message.no_file_selected"))
            return

        # 根据模式确定要覆盖的目标文件
        if self.mode_var.get() == Mode.JP_TO_GLOBAL:
            target_files = self.jp_files_listbox.file_list
        else:
            # GLOBAL_TO_JP 和 LEGACY_BATCH 模式：使用被替换的原始文件列表
            target_files = self.replaced_source_files

        if not target_files:
            messagebox.showerror(t("common.error"), t("message.list_empty"))
            return

        # 检查输出文件是否存在
        for output_path in self.final_output_paths:
            if not output_path.exists():
                messagebox.showerror(t("common.error"), t("message.file_not_found", path=output_path))
                return

        # 在主线程中显示确认对话框
        files_to_replace = []
        for i, output_path in enumerate(self.final_output_paths):
            if i < len(target_files):
                target_file = target_files[i]
                files_to_replace.append(f"  {target_file.name}")

        files_list = "\n".join(files_to_replace)

        confirm_message = t("message.confirm_replace_files", count=len(files_to_replace), files=files_list)

        # 显示确认对话框，如果用户确认则执行覆盖
        if messagebox.askyesno(t("common.warning"), confirm_message):
            self.run_in_thread(self.replace_original)

    def replace_original(self):
        """实际的覆盖逻辑"""
        if self.mode_var.get() == Mode.JP_TO_GLOBAL:
            target_files = self.jp_files_listbox.file_list
        else:
            # GLOBAL_TO_JP 和 LEGACY_BATCH 模式：使用被替换的原始文件列表
            target_files = self.replaced_source_files

        # 只有一个文件时，使用 replace_file
        if len(self.final_output_paths) == 1 and len(target_files) >= 1:
            success = replace_file(
                source_path=self.final_output_paths[0],
                dest_path=target_files[0],
                create_backup=self.app.create_backup_var.get(),
                ask_confirm=False,  # 已经在上一步确认过了
                log=self.logger.log,
            )

            # 更新状态栏
            if success:
                self.logger.status(t("status.done"))
            else:
                self.logger.status(t("status.failed"))
        else:
            # 多个文件时，使用 replace_files
            file_pairs: list[tuple[Path, Path]] = []
            for i, output_path in enumerate(self.final_output_paths):
                if i < len(target_files):
                    file_pairs.append((output_path, target_files[i]))

            success_count, fail_count = replace_files(
                file_pairs=file_pairs,
                create_backup=self.app.create_backup_var.get(),
                ask_confirm=False,  # 已经在上一步确认过了
                log=self.logger.log,
            )

            self.logger.status(t("status.done"))
        
        # 覆盖完成后禁用按钮
        if self.mode_var.get() == Mode.LEGACY_BATCH:
            self.master.after(0, lambda: self.batch_replace_button.config(state=tk.DISABLED))
        else:
            self.master.after(0, lambda: self.replace_button.config(state=tk.DISABLED))
    
    def run_conversion(self):
        # 根据模式分发到不同的处理函数
        if self.mode_var.get() == Mode.LEGACY_BATCH:
            self._run_batch_conversion()
        else:
            self._run_single_conversion()

    def _run_single_conversion(self):
        """处理 JP_TO_GLOBAL 和 GLOBAL_TO_JP 模式"""
        # 1. 验证输入
        output_dir = Path(self.app.output_dir_var.get())
        jp_files = self.jp_files_listbox.file_list
        
        if not self.global_zone.path:
            messagebox.showerror(t("common.error"), t("message.no_file_selected"))
            return
        if not jp_files:
            messagebox.showerror(t("common.error"), t("message.list_empty"))
            return

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.logger.log(f'❌ {t("message.create_dir_failed_detail",path=output_dir, error=e)}')
            return
        
        # 重置输出文件路径列表和按钮状态
        self.final_output_paths = []
        self.replaced_source_files = []
        self.master.after(0, lambda: self.replace_button.config(state=tk.DISABLED))
        
        # 2. 准备选项
        crc_setting = self.app.enable_crc_correction_var.get()
        perform_crc = False
        
        if crc_setting == "auto":
            target_bundle = self.global_zone.path if self.mode_var.get() == Mode.JP_TO_GLOBAL else jp_files[0]
            platform, unity_version = core.get_unity_platform_info(target_bundle)
            self.logger.log(t("log.platform_info", platform=platform, version=unity_version))
            perform_crc = (platform == "StandaloneWindows64")
        elif crc_setting == "true":
            perform_crc = True
        
        save_options = core.SaveOptions(
            perform_crc=perform_crc,
            extra_bytes=self.app.get_extra_bytes(),
            compression=self.app.compression_method_var.get()
        )
        
        # 从设置页获取资源类型
        asset_types_to_replace = set()
        if self.app.replace_all_var.get():
            asset_types_to_replace = {"ALL"}
        else:
            if self.app.replace_texture2d_var.get(): asset_types_to_replace.add("Texture2D")
            if self.app.replace_textasset_var.get(): asset_types_to_replace.add("TextAsset")
            if self.app.replace_mesh_var.get(): asset_types_to_replace.add("Mesh")
        
        # 3. 调用处理函数
        self.logger.status(t("common.processing"))
        if self.mode_var.get() == Mode.JP_TO_GLOBAL:
            success, message = core.process_jp_to_global_conversion(
                global_bundle_path=self.global_zone.path,
                jp_bundle_paths=jp_files,
                output_dir=output_dir,
                save_options=save_options,
                asset_types_to_replace=asset_types_to_replace,
                log=self.logger.log
            )

            # 记录输出文件路径（JP_TO_GLOBAL 模式只输出一个文件）
            if success:
                output_path = output_dir / self.global_zone.path.name
                if output_path.exists():
                    self.final_output_paths.append(output_path)
                    # 启用覆盖按钮
                    self.master.after(0, lambda: self.replace_button.config(state=tk.NORMAL))
        else:  # GLOBAL_TO_JP
            success, message, replaced_files = core.process_global_to_jp_conversion(
                global_bundle_path=self.global_zone.path,
                jp_template_paths=jp_files,
                output_dir=output_dir,
                save_options=save_options,
                asset_types_to_replace=asset_types_to_replace,
                log=self.logger.log
            )

            # 记录输出文件路径和被替换的原始文件路径
            if success:
                self.replaced_source_files = replaced_files
                for src_file in replaced_files:
                    output_path = output_dir / src_file.name
                    if output_path.exists():
                        self.final_output_paths.append(output_path)

                # 如果有输出文件，启用覆盖按钮
                if self.final_output_paths:
                    self.master.after(0, lambda: self.replace_button.config(state=tk.NORMAL))
        
        # 4. 结果反馈
        if success:
            self.logger.status(t("status.done"))
            messagebox.showinfo(t("common.success"), message)
        else:
            self.logger.status(t("status.failed"))
            messagebox.showerror(t("common.fail"), message)
    
    def _run_batch_conversion(self):
        """批量处理旧版到新版国际服的转换"""
        output_dir = Path(self.app.output_dir_var.get())
        
        if not self.legacy_file_list:
            messagebox.showerror(t("common.error"), t("message.list_empty"))
            return
        
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.logger.log(f'❌ {t("message.create_dir_failed_detail",path=output_dir, error=e)}')
            return
        
        # 重置输出文件路径列表和按钮状态
        self.final_output_paths = []
        self.replaced_source_files = []
        self.master.after(0, lambda: self.batch_replace_button.config(state=tk.DISABLED))
        
        # 准备选项
        crc_setting = self.app.enable_crc_correction_var.get()
        perform_crc = False
        
        if crc_setting == "auto":
            target_bundle = self.legacy_file_list[0]
            platform, unity_version = core.get_unity_platform_info(target_bundle)
            self.logger.log(t("log.platform_info", platform=platform, version=unity_version))
            perform_crc = (platform == "StandaloneWindows64")
        elif crc_setting == "true":
            perform_crc = True
        
        save_options = core.SaveOptions(
            perform_crc=perform_crc,
            extra_bytes=self.app.get_extra_bytes(),
            compression=self.app.compression_method_var.get()
        )
        
        # 从设置页获取资源类型
        asset_types_to_replace = set()
        if self.app.replace_all_var.get():
            asset_types_to_replace = {"ALL"}
        else:
            if self.app.replace_texture2d_var.get(): asset_types_to_replace.add("Texture2D")
            if self.app.replace_textasset_var.get(): asset_types_to_replace.add("TextAsset")
            if self.app.replace_mesh_var.get(): asset_types_to_replace.add("Mesh")
        
        base_game_dir = Path(self.app.game_resource_dir_var.get())
        search_paths = get_search_resource_dirs(base_game_dir, self.app.auto_detect_subdirs_var.get())
        
        self.logger.status(t("common.processing"))
        
        # 调用批量处理函数
        success_count, fail_count, failed_tasks, all_output_paths, all_replaced_files = core.process_batch_legacy_batch(
            legacy_file_list=self.legacy_file_list,
            search_paths=search_paths,
            output_dir=output_dir,
            asset_types_to_replace=asset_types_to_replace,
            save_options=save_options,
            log=self.logger.log,
            progress_callback=lambda current, total, filename: self.logger.status(
                t("status.processing_batch", current=current, total=total, filename=filename)
            )
        )
        
        # 记录输出文件路径和被替换的原始文件路径
        self.final_output_paths = all_output_paths
        self.replaced_source_files = all_replaced_files
        
        total_files = len(self.legacy_file_list)
        self.logger.log(t("log.mod_update.batch_summary", total=total_files, success=success_count, fail=fail_count))
        
        if failed_tasks:
            self.logger.log(t("log.mod_update.failed_items_cnt", count=fail_count))
            failed_list = "\n".join([t("log.mod_update.failed_item", filename=f) for f in failed_tasks])
            self.logger.log(failed_list)
        
        # 如果有成功处理的文件，启用覆盖按钮
        if self.final_output_paths:
            self.master.after(0, lambda: self.batch_replace_button.config(state=tk.NORMAL))
        
        self.logger.status(t("status.done"))
        messagebox.showinfo(t("common.success"), t("message.batch_success", success=success_count, fail=fail_count))