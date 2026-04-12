# gui/tabs/crc_tool_tab.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path
import shutil

from ...i18n import t
from ..base_tab import TabFrame
from ..components import DropZone, UIComponents, SettingRow
from ..utils import replace_file
from ...utils import CRCUtils, get_search_resource_dirs
from ...naming import parse_filename

class CrcToolTab(TabFrame):
    def create_widgets(self):
        # 待修正文件
        self.modified_zone = DropZone(
            self, title=t("ui.label.modified_file"),
            placeholder_text=t("ui.crc_tool.placeholder_modified"),
            on_file_selected=self.on_modified_selected,
            filetypes=[(t("file_type.bundle"), "*.bundle"), (t("file_type.all_files"), "*.*")],
            logger=self.logger
        )

        # 目标 CRC 输入框
        self.target_crc_var = tk.StringVar()
        SettingRow.create_entry_row(
            self,
            label=t("ui.label.target_crc"),
            text_var=self.target_crc_var,
            placeholder_text=t("ui.crc_tool.target_crc_placeholder"),
            expand=True
        )

        # 原始文件
        self.original_zone = DropZone(
            self, title=t("ui.label.original_file"),
            placeholder_text=t("ui.crc_tool.placeholder_origin"),
            on_file_selected=self.on_original_selected,
            filetypes=[(t("file_type.bundle"), "*.bundle"), (t("file_type.all_files"), "*.*")],
            search_path_var=self.app.game_resource_dir_var,
            logger=self.logger
        )

        # 操作按钮
        action_button_frame = tb.Frame(self)
        action_button_frame.pack(fill=tk.X, pady=10)
        action_button_frame.grid_columnconfigure((0, 1, 2), weight=1)
        
        UIComponents.create_button(action_button_frame, t("action.run_crc_correction"), self.run_correction_thread,
                                   bootstyle="success", style="large").grid(row=0, column=0, sticky="ew", padx=5)
        UIComponents.create_button(action_button_frame, t("action.calculate_crc"), self.calculate_values_thread,
                                   bootstyle="primary", style="large").grid(row=0, column=1, sticky="ew", padx=5)  
        self.replace_button = UIComponents.create_button(action_button_frame, t("action.replace_original"), self.replace_original_thread, bootstyle="danger", state="disabled", style="large")
        self.replace_button.grid(row=0, column=2, sticky="ew", padx=5)

    def on_original_selected(self, path: Path):
        """原始文件选中后的处理"""
        self.logger.log(t("log.crc.loaded_original", file=path))
        self.logger.status(t("status.loaded", type="original"))

    def on_modified_selected(self, path: Path):
        """待修正文件选中后的处理"""
        self.logger.log(t("log.crc.loaded_modified", file=path))
        
        # 从文件名提取目标 CRC
        parsed_crc = parse_filename(path.name).crc
        if parsed_crc:
            target_crc = int(parsed_crc)
            self.target_crc_var.set(f"{target_crc:08X}")
        
        # 清除旧的 original_file，准备重新搜索
        self.original_zone.clear()
        
        # 自动搜索 original 文件
        game_dir_str = self.app.game_resource_dir_var.get()
        if not game_dir_str:
            self.logger.log(f'⚠️ {t("log.game_dir_not_set")}')
            return

        base_game_dir = Path(game_dir_str)
        search_dirs = get_search_resource_dirs(base_game_dir, self.app.auto_detect_subdirs_var.get())

        for directory in search_dirs:
            if not directory.is_dir():
                continue
            
            candidate = directory / path.name
            if candidate.exists():
                self.original_zone.set_path(candidate)
                self.logger.log(t("log.file_found_in_subdir", subdir=directory.name, filename=candidate.name))
                return
        
        self.logger.log(f'⚠️ {t("log.file_not_found_in_dirs", filename=path.name)}')

    def _validate_paths(self):
        if not self.modified_zone.path:
            messagebox.showerror(t("common.error"), t("message.crc.provide_at_least_one_file"))
            return False
        return True

    def _validate_target_crc(self) -> int | None:
        """验证并解析目标 CRC 值"""
        crc_str = self.target_crc_var.get().strip().removeprefix("0x")
        if not crc_str:
            messagebox.showerror(t("common.error"), t("message.crc.provide_at_least_one_file"))
            return None
        try:
            return int(crc_str, 16)
        except ValueError:
            messagebox.showerror(t("common.error"), t("message.crc.calculation_error", error="Invalid CRC format"))
            return None

    def run_correction_thread(self):
        if self._validate_paths(): 
            self.run_in_thread(self.run_correction)

    def calculate_values_thread(self):
        if not self.original_zone.path and not self.modified_zone.path:
            messagebox.showerror(t("common.error"), t("message.crc.provide_at_least_one_file"))
            return
        
        if bool(self.original_zone.path) != bool(self.modified_zone.path):
            self.run_in_thread(self.calculate_single_value)
        # 如果两个文件都有，计算两个文件的CRC32值并进行比较
        else:
            self.run_in_thread(self.calculate_values)

    def replace_original_thread(self):
        if not self.original_zone.path:
            messagebox.showerror(t("common.error"), t("message.crc.provide_at_least_one_file"))
            return
        self.run_in_thread(self.replace_original)

    def run_correction(self):
        self.final_output_path = None
        self.master.after(0, lambda: self.replace_button.config(state=tk.DISABLED))
        
        self.logger.log("\n" + "="*50)
        self.logger.log(t("log.crc.start_correction"))
        self.logger.status(t("common.processing"))
        try:
            # 确保有输出目录变量
            if not self.app.output_dir_var or not self.app.output_dir_var.get():
                self.logger.log(f'❌ {t("log.output_dir_not_set")}')
                messagebox.showerror(t("common.error"), t("message.output_dir_not_set"))
                self.logger.status(t("status.failed"))
                return False
            
            # 创建输出目录（如果不存在）
            output_dir = Path(self.app.output_dir_var.get())
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 获取目标 CRC
            target_crc = self._validate_target_crc()
            if target_crc is None:
                return False
            
            # 检测当前文件 CRC 是否已匹配目标
            current_crc = CRCUtils.compute_crc32(self.modified_zone.path)
            
            if current_crc == target_crc:
                self.logger.log(f'⚠️ {t("log.crc.match_no_correction_needed")}')
                messagebox.showinfo(t("common.result"), t("message.crc.match_no_correction_needed"))
                self.logger.status(t("status.calculation_done"))
                if self.original_zone.path:
                    self.master.after(0, lambda: self.replace_button.config(state=tk.NORMAL))
                return True
            
            output_filename = self.modified_zone.path.name
            output_path = output_dir / output_filename
            
            shutil.copy2(self.modified_zone.path, output_path)
            self.logger.log(t("log.file.saved", path=output_path))
            
            success = CRCUtils.manipulate_file_crc(output_path, target_crc, self.app.get_extra_bytes())
            
            if success:
                self.final_output_path = output_path
                self.logger.log(t("log.crc.correction_success"))
                if self.original_zone.path:
                    self.logger.log(t("log.replace_original", button=t('action.replace_original')))
                    self.master.after(0, lambda: self.replace_button.config(state=tk.NORMAL))
                messagebox.showinfo(t("common.success"), t("message.crc.correction_success", path=output_path))
            else:
                self.logger.log(f'❌ {t("log.crc.correction_failed")}')
                messagebox.showerror(t("common.fail"), t("message.crc.correction_failed"))
            self.logger.status(t("status.done"))
            return success
                
        except Exception as e:
            self.logger.log(t("log.error_detail", error=e))
            self.logger.status(t("status.error", error=e))
            messagebox.showerror(t("common.error"), t("message.execution_error", error=e))
            return False
        
    def calculate_single_value(self):
        """计算单个文件的CRC32值"""
        self.logger.status(t("common.processing"))
        try:
            target_path = self.modified_zone.path if self.modified_zone.path else self.original_zone.path

            crc_value = CRCUtils.compute_crc32(target_path)
            crc_str = f"{crc_value}(0x{crc_value:08X})"

            self.logger.log(t("log.crc.file_crc32", crc=crc_str))
            self.logger.status(t("status.calculation_done"))
            messagebox.showinfo(t("common.result"), t("message.crc.file_crc32", crc=crc_str))
            
        except Exception as e:
            self.logger.log(f'❌ {t("log.crc.calculation_error", error=e)}')
            self.logger.status(t("status.error", error=e))
            messagebox.showerror(t("common.error"), t("message.crc.calculation_error", error=e))

    def calculate_values(self):
        """计算两个文件的CRC32值，并判断是否匹配"""
        self.logger.status(t("common.processing"))
        try:
            is_match, original_crc_value, modified_crc_value = CRCUtils.check_crc_match(
                self.original_zone.path, self.modified_zone.path
            )

            original_crc_str = f"{original_crc_value}(0x{original_crc_value:08X})"
            modified_crc_str = f"{modified_crc_value}(0x{modified_crc_value:08X})"

            self.logger.log(t("log.crc.modified_file_crc32", crc=modified_crc_str))
            self.logger.log(t("log.crc.original_file_crc32", crc=original_crc_str))

            msg = f"{t('message.crc.modified_file_crc32', crc=modified_crc_str)}\n{t('message.crc.original_file_crc32', crc=original_crc_str)}\n"

            self.logger.status(t("status.calculation_done"))
            if is_match:
                self.logger.log(t("log.crc.match_yes"))
                messagebox.showinfo(t("common.result"), f"{msg}{t('message.crc.match_yes')}")
            else:
                self.logger.log(t("log.crc.match_no"))
                messagebox.showwarning(t("common.result"), f"{msg}{t('message.crc.match_no')}")
        except Exception as e:
            self.logger.log(f'❌ {t("log.crc.calculation_error", error=e)}')
            self.logger.status(t("status.error", error=e))
            messagebox.showerror(t("common.error"), t("message.crc.calculation_error", error=e))

    def replace_original(self):
        if self.final_output_path and self.final_output_path.exists():
            source_path = self.final_output_path
        else:
            source_path = self.modified_zone.path
            
        replace_file(
            source_path=source_path,
            dest_path=self.original_zone.path,
            create_backup=self.app.create_backup_var.get(),
            ask_confirm=True,
            confirm_message=t("message.confirm_replace_file", path=self.original_zone.path.name),
            log=self.logger.log,
        )