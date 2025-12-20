# ui/tabs/crc_tool_tab.py

import tkinter as tk
from tkinter import messagebox, filedialog
from pathlib import Path
import shutil

from i18n import t
from ui.base_tab import TabFrame
from ui.components import Theme, UIComponents
from ui.utils import is_multiple_drop, replace_file, select_file
from utils import CRCUtils, get_search_resource_dirs

class CrcToolTab(TabFrame):
    def create_widgets(self):
        self.original_path = None
        self.modified_path = None

        # 1. 待修正文件
        _, self.modified_label = UIComponents.create_file_drop_zone(
            self, t("ui.label.modified_file"), self.drop_modified, self.browse_modified,
            clear_cmd=self.clear_callback('modified_path')
        )

        # 2. 原始文件 - 使用新的 search_path_var 参数来显示查找路径
        original_frame, self.original_label = UIComponents.create_file_drop_zone(
            self, t("ui.label.original_file"), self.drop_original, self.browse_original,
            search_path_var=self.app.game_resource_dir_var,
            clear_cmd=self.clear_callback('original_path')
        )
        
        # 自定义拖放区的提示文本，使其更具指导性
        self.original_label.config(text=t("ui.mod_update.placeholder_new"))

        # 3. 操作按钮
        action_button_frame = tk.Frame(self) # 使用与父框架相同的背景色
        action_button_frame.pack(fill=tk.X, pady=10)
        action_button_frame.grid_columnconfigure((0, 1, 2), weight=1)
        
        UIComponents.create_button(action_button_frame, t("action.run_crc_correction"), self.run_correction_thread,
                                   bg_color=Theme.BUTTON_SUCCESS_BG, padx=10, pady=5).grid(row=0, column=0, sticky="ew", padx=5)
        UIComponents.create_button(action_button_frame, t("action.calculate_crc"), self.calculate_values_thread,
                                   bg_color=Theme.BUTTON_PRIMARY_BG, padx=10, pady=5).grid(row=0, column=1, sticky="ew", padx=5)
        UIComponents.create_button(action_button_frame, t("action.replace_original"), self.replace_original_thread,
                                   bg_color=Theme.BUTTON_DANGER_BG, padx=10, pady=5).grid(row=0, column=2, sticky="ew", padx=5)

    def drop_original(self, event):
        if is_multiple_drop(event.data):
            messagebox.showwarning(t("message.invalid_operation"), t("message.drop_single_file"))
            return
        self.set_original_file(Path(event.data.strip('{}')))

    def browse_original(self):
        select_file(
            title=t("ui.dialog.select", type=t("ui.label.original_file")),
            filetypes=[(t("file_type.bundle"), "*.bundle"), (t("file_type.all_files"), "*.*")],
            callback=self.set_original_file,
            logger=self.logger.log
        )
    
    def drop_modified(self, event):
        if is_multiple_drop(event.data):
            messagebox.showwarning(t("message.invalid_operation"), t("message.drop_single_file"))
            return
        self.set_modified_file(Path(event.data.strip('{}')))
    def browse_modified(self):
        select_file(
            title=t("ui.dialog.select", type=t("ui.label.modified_file")),
            filetypes=[(t("file_type.bundle"), "*.bundle"), (t("file_type.all_files"), "*.*")],
            callback=self.set_modified_file,
            logger=self.logger.log
        )

    def set_original_file(self, path: Path):
        self.original_path = path
        self.original_label.config(text=f"{path.name}", fg=Theme.COLOR_SUCCESS)
        self.logger.log(t("log.crc.loaded_original", file=path))
        self.logger.status(t("log.status.loaded", type="original"))

    def set_modified_file(self, path: Path):
        self.modified_path = path
        self.modified_label.config(text=f"{path.name}", fg=Theme.COLOR_SUCCESS)
        self.logger.log(t("log.crc.loaded_modified", file=path))
        
        game_dir_str = self.app.game_resource_dir_var.get()
        if not game_dir_str:
            self.logger.log(t("log.game_dir_not_set"))
            return

        base_game_dir = Path(game_dir_str)
        if not base_game_dir.is_dir():
            self.logger.log(t("log.game_dir_not_exist", path=game_dir_str))
            return
        
        # 构造搜索目录列表
        search_dirs = get_search_resource_dirs(base_game_dir, self.app.auto_detect_subdirs_var.get())

        found = False
        for directory in search_dirs:
            if not directory.is_dir():
                continue # 跳过不存在的子目录
            
            candidate = directory / path.name
            if candidate.exists():
                self.set_original_file(candidate)
                self.logger.log(t("log.file_found_in_subdir", subdir=directory.name, filename=candidate.name))
                found = True
                break # 找到后即停止搜索
        
        if not found:
            self.logger.log(t("log.file_not_found_in_dirs", filename=path.name))

    def _validate_paths(self):
        if not self.original_path or not self.modified_path:
            messagebox.showerror(t("common.error"), t("message.crc.provide_both_files"))
            return False
        return True

    def run_correction_thread(self):
        if self._validate_paths(): self.run_in_thread(self.run_correction)

    def calculate_values_thread(self):
        # 检查路径情况 - 至少需要设置一个文件路径
        if not self.original_path and not self.modified_path:
            messagebox.showerror(t("common.error"), t("message.crc.provide_at_least_one_file"))
            return
        
        # 如果只有一个文件路径被设置，计算单个文件的CRC32值
        if bool(self.original_path) != bool(self.modified_path):
            self.run_in_thread(self.calculate_single_value)
        # 如果两个文件都有，计算两个文件的CRC32值并进行比较
        else:
            self.run_in_thread(self.calculate_values)

    def replace_original_thread(self):
        if self._validate_paths(): self.run_in_thread(self.replace_original)

    def run_correction(self):
        self.logger.log("\n" + "="*50)
        self.logger.log(t("log.crc.start_correction"))
        self.logger.status(t("common.processing"))
        try:
            # 确保有输出目录变量
            if not self.app.output_dir_var or not self.app.output_dir_var.get():
                self.logger.log(t("log.output_dir_not_set"))
                messagebox.showerror(t("common.error"), t("message.output_dir_not_set"))
                self.logger.status(t("log.status.failed"))
                return False
            
            # 创建输出目录（如果不存在）
            output_dir = Path(self.app.output_dir_var.get())
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 先检测CRC是否一致
            try:
                is_crc_match = CRCUtils.check_crc_match(self.original_path, self.modified_path)
            except Exception as e:
                self.logger.log(t("log.crc.check_failed", error=e))
                messagebox.showerror(t("common.error"), t("message.crc.check_failed"))
                self.logger.status(t("log.status.error", error=e))
                return False
            
            if is_crc_match:
                self.logger.log(t("log.crc.match_no_correction_needed"))
                messagebox.showinfo(t("common.result"), t("message.crc.match_no_correction_needed"))
                self.logger.status(t("log.status.calculation_done"))
                return True
            
            # 计算输出文件路径
            output_filename = self.modified_path.name
            output_path = output_dir / output_filename
            
            # 先复制修改后的文件到输出目录
            shutil.copy2(self.modified_path, output_path)
            self.logger.log(t("log.file.saved", path=output_path))
            
            # 修正输出目录中的文件CRC
            success = CRCUtils.manipulate_crc(self.original_path, output_path, self.app.enable_padding_var.get())
            
            if success:
                self.logger.log(t("log.crc.correction_success"))
                messagebox.showinfo(t("common.success"), t("message.crc.correction_success", path=output_path))
            else:
                self.logger.log(t("log.crc.correction_failed"))
                messagebox.showerror(t("common.fail"), t("message.crc.correction_failed"))
            self.logger.status(t("log.status.done"))
            return success
                
        except Exception as e:
            self.logger.log(t("log.error_detail", error=e))
            self.logger.status(t("log.status.error", error=e))
            messagebox.showerror(t("common.error"), t("message.execution_error", error=e))
            return False
        
    def calculate_single_value(self):
        """计算单个文件的CRC32值"""
        self.logger.status(t("common.processing"))
        try:
            # 确定要计算的文件路径
            target_path = self.modified_path if self.modified_path else self.original_path
            
            with open(target_path, "rb") as f: file_data = f.read()
            crc_hex = f"{CRCUtils.compute_crc32(file_data):08X}"
            
            self.logger.log(t(f"log.crc.file_crc32", crc=crc_hex))
            self.logger.status(t("log.status.calculation_done"))
            messagebox.showinfo(t("common.result"), t(f"message.crc.file_crc32", crc=crc_hex))
            
        except Exception as e:
            self.logger.log(t("log.crc.calculation_error", error=e))
            self.logger.status(t("log.status.error", error=e))
            messagebox.showerror(t("common.error"), t("message.crc.calculation_error", error=e))

    def calculate_values(self):
        """计算两个文件的CRC32值，并判断是否匹配"""
        self.logger.status(t("common.processing"))
        try:
            with open(self.original_path, "rb") as f: original_data = f.read()
            with open(self.modified_path, "rb") as f: modified_data = f.read()

            original_crc_hex = f"{CRCUtils.compute_crc32(original_data):08X}"
            modified_crc_hex = f"{CRCUtils.compute_crc32(modified_data):08X}"
            
            self.logger.log(t("log.crc.modified_file_crc32", crc=modified_crc_hex))
            self.logger.log(t("log.crc.original_file_crc32", crc=original_crc_hex))

            msg = f"{t('message.crc.modified_file_crc32', crc=modified_crc_hex)}\n{t('message.crc.original_file_crc32', crc=original_crc_hex)}\n"

            self.logger.status(t("log.status.calculation_done"))
            if original_crc_hex == modified_crc_hex:
                self.logger.log(t("log.crc.match_yes"))
                messagebox.showinfo(t("common.result"), f"{msg}{t('message.crc.match_yes')}")
            else:
                self.logger.log(t("log.crc.match_no"))
                messagebox.showwarning(t("common.result"), f"{msg}{t('message.crc.match_no')}")
        except Exception as e:
            self.logger.log(t("log.crc.calculation_error", error=e))
            self.logger.status(t("log.status.error", error=e))
            messagebox.showerror(t("common.error"), t("message.crc.calculation_error", error=e))

    def replace_original(self):
        success = replace_file(
            source_path=self.modified_path,
            dest_path=self.original_path,
            create_backup=self.app.create_backup_var.get(),
            ask_confirm=True,
            confirm_message=t("message.confirm_replace_file", path=self.original_path.name),
            log=self.logger.log,
        )