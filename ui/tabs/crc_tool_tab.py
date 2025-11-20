# ui/tabs/crc_tool_tab.py

import tkinter as tk
from tkinter import messagebox, filedialog
from pathlib import Path
import shutil

from ui.base_tab import TabFrame
from ui.components import Theme, UIComponents
from ui.utils import is_multiple_drop, replace_file
from utils import CRCUtils

class CrcToolTab(TabFrame):
    def create_widgets(self, game_resource_dir_var, enable_padding_var, create_backup_var, auto_detect_subdirs_var, output_dir_var=None):
        self.original_path = None
        self.modified_path = None
        self.enable_padding = enable_padding_var
        self.create_backup = create_backup_var
        # 接收共享的游戏资源目录变量
        self.game_resource_dir_var = game_resource_dir_var
        self.auto_detect_subdirs = auto_detect_subdirs_var
        # 接收输出目录变量
        self.output_dir_var = output_dir_var

        # 1. 待修正文件
        _, self.modified_label = UIComponents.create_file_drop_zone(
            self, "待修正文件", self.drop_modified, self.browse_modified
        )

        # 2. 原始文件 - 使用新的 search_path_var 参数来显示查找路径
        original_frame, self.original_label = UIComponents.create_file_drop_zone(
            self, "原始文件", self.drop_original, self.browse_original, 
            search_path_var=self.game_resource_dir_var
        )
        
        # 自定义拖放区的提示文本，使其更具指导性
        self.original_label.config(text="拖入修改后文件后将自动查找原始文件\n或手动拖放/浏览文件")

        # 3. 操作按钮
        action_button_frame = tk.Frame(self) # 使用与父框架相同的背景色
        action_button_frame.pack(fill=tk.X, pady=10)
        action_button_frame.grid_columnconfigure((0, 1, 2), weight=1)
        
        UIComponents.create_button(action_button_frame, "运行CRC修正", self.run_correction_thread, 
                                   bg_color=Theme.BUTTON_SUCCESS_BG, padx=10, pady=5).grid(row=0, column=0, sticky="ew", padx=5)
        UIComponents.create_button(action_button_frame, "计算CRC值", self.calculate_values_thread, 
                                   bg_color=Theme.BUTTON_PRIMARY_BG, padx=10, pady=5).grid(row=0, column=1, sticky="ew", padx=5)
        UIComponents.create_button(action_button_frame, "替换原始文件", self.replace_original_thread, 
                                   bg_color=Theme.BUTTON_DANGER_BG, padx=10, pady=5).grid(row=0, column=2, sticky="ew", padx=5)

    def drop_original(self, event): 
        if is_multiple_drop(event.data):
            messagebox.showwarning("操作无效", "请一次只拖放一个文件。")
            return
        self.set_original_file(Path(event.data.strip('{}')))
    def browse_original(self):
        p = filedialog.askopenfilename(title="请选择原始文件")
        if p: 
            self.set_original_file(Path(p))
    
    def drop_modified(self, event): 
        if is_multiple_drop(event.data):
            messagebox.showwarning("操作无效", "请一次只拖放一个文件。")
            return
        self.set_modified_file(Path(event.data.strip('{}')))
    def browse_modified(self):
        p = filedialog.askopenfilename(title="请选择修改后文件")
        if p: 
            self.set_modified_file(Path(p))

    def set_original_file(self, path: Path):
        self.original_path = path
        self.original_label.config(text=f"{path.name}", fg=Theme.COLOR_SUCCESS)
        self.logger.log(f"已加载CRC原始文件: {path.name}")
        self.logger.status("已加载CRC原始文件")

    def set_modified_file(self, path: Path):
        self.modified_path = path
        self.modified_label.config(text=f"{path.name}", fg=Theme.COLOR_SUCCESS)
        self.logger.log(f"已加载CRC修改后文件: {path.name}")
        
        game_dir_str = self.game_resource_dir_var.get()
        if not game_dir_str:
            self.logger.log("⚠️ 警告: 未设置游戏资源目录，无法自动寻找原始文件。")
            return

        base_game_dir = Path(game_dir_str)
        if not base_game_dir.is_dir():
            self.logger.log(f"⚠️ 警告: 游戏资源目录 '{game_dir_str}' 不存在。")
            return
        
        # 使用通用函数构造搜索目录列表
        search_dirs = self.get_game_search_dirs(base_game_dir, self.auto_detect_subdirs.get())

        found = False
        for directory in search_dirs:
            if not directory.is_dir():
                continue # 跳过不存在的子目录
            
            candidate = directory / path.name
            if candidate.exists():
                self.set_original_file(candidate)
                self.logger.log(f"已在 '{directory.name}' 中自动找到并加载原始文件: {candidate.name}")
                found = True
                break # 找到后即停止搜索
        
        if not found:
            self.logger.log(f"⚠️ 警告: 未能在指定的资源目录中找到对应的原始文件 '{path.name}'。")

    def _validate_paths(self):
        if not self.original_path or not self.modified_path:
            messagebox.showerror("错误", "请同时提供原始文件和待修正文件。")
            return False
        return True

    def run_correction_thread(self):
        if self._validate_paths(): self.run_in_thread(self.run_correction)

    def calculate_values_thread(self):
        # 检查路径情况
        if not self.modified_path:
            messagebox.showerror("错误", "请至少提供一个文件路径。")
            return
        
        # 如果只有修改后文件，计算其CRC32值
        if not self.original_path:
            self.run_in_thread(self.calculate_single_value)
        # 如果两个文件都有，保持原有行为
        else:
            self.run_in_thread(self.calculate_values)

    def replace_original_thread(self):
        if self._validate_paths(): self.run_in_thread(self.replace_original)

    def run_correction(self):
        self.logger.log("\n" + "="*50)
        self.logger.log("开始CRC修正过程...")
        self.logger.status("正在进行CRC修正...")
        try:
            # 确保有输出目录变量
            if not self.output_dir_var or not self.output_dir_var.get():
                self.logger.log("❌ 错误: 未设置输出目录")
                messagebox.showerror("错误", "未设置输出目录，请先在设置中配置输出目录。")
                self.logger.status("CRC修正失败")
                return False
            
            # 创建输出目录（如果不存在）
            output_dir = Path(self.output_dir_var.get())
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 先检测CRC是否一致
            self.logger.log("正在检测CRC值是否匹配...")
            try:
                is_crc_match = CRCUtils.check_crc_match(self.original_path, self.modified_path)
            except Exception as e:
                self.logger.log(f"⚠️ 警告: 检测CRC值时发生错误: {e}")
                messagebox.showerror("错误", "检测CRC值时发生错误。请检查原始文件和修改后文件是否正确。")
                self.logger.status("CRC检测失败")
                return False
            
            
            if is_crc_match:
                self.logger.log("✅ CRC值已匹配，无需修正")
                messagebox.showinfo("CRC检测结果", "CRC值已匹配，无需进行修正操作。")
                self.logger.status("CRC检测完成")
                return True
            
            self.logger.log("❌ CRC值不匹配，开始进行CRC修正...")
            
            # 计算输出文件路径
            output_filename = self.modified_path.name
            output_path = output_dir / output_filename
            
            # 先复制修改后的文件到输出目录
            shutil.copy2(self.modified_path, output_path)
            self.logger.log(f"已将修改后的文件复制到输出目录: {output_path}")
            
            # 修正输出目录中的文件CRC
            success = CRCUtils.manipulate_crc(self.original_path, output_path, self.enable_padding.get())
            
            if success:
                self.logger.log("✅ CRC修正成功！")
                messagebox.showinfo("成功", f"CRC 修正成功！\n修正后的文件已保存至输出目录:\n{output_path}")
            else:
                self.logger.log("❌ CRC修正失败")
                messagebox.showerror("失败", "CRC 修正失败。")
            self.logger.status("CRC修正完成")
            return success
                
        except Exception as e:
            self.logger.log(f"❌ 错误：{e}")
            messagebox.showerror("错误", f"执行过程中发生错误:\n{e}")
            self.logger.status("CRC修正失败")
            return False
        
    def calculate_single_value(self):
        """计算单个文件的CRC32值"""
        self.logger.status("正在计算CRC...")
        try:
            with open(self.modified_path, "rb") as f: file_data = f.read()

            crc_hex = f"{CRCUtils.compute_crc32(file_data):08X}"
            
            self.logger.log(f"文件 CRC32: {crc_hex}")
            messagebox.showinfo("CRC计算结果", f"文件 CRC32: {crc_hex}")
            
        except Exception as e:
            self.logger.log(f"❌ 计算CRC时发生错误: {e}")
            messagebox.showerror("错误", f"计算CRC时发生错误:\n{e}")

    def calculate_values(self):
        """计算两个文件的CRC32值，并判断是否匹配"""
        self.logger.status("正在计算CRC...")
        try:
            with open(self.original_path, "rb") as f: original_data = f.read()
            with open(self.modified_path, "rb") as f: modified_data = f.read()

            original_crc_hex = f"{CRCUtils.compute_crc32(original_data):08X}"
            modified_crc_hex = f"{CRCUtils.compute_crc32(modified_data):08X}"
            
            self.logger.log(f"待修正文件 CRC32: {modified_crc_hex}")
            self.logger.log(f"原始文件 CRC32: {original_crc_hex}")

            msg = f"待修正文件 CRC32: {modified_crc_hex}\n原始文件 CRC32: {original_crc_hex}\n"

            if original_crc_hex == modified_crc_hex:
                self.logger.log("    CRC值匹配: ✅是")
                messagebox.showinfo("CRC计算结果", f"{msg}\n✅ CRC值匹配: 是")
            else:
                self.logger.log("    CRC值匹配: ❌否")
                messagebox.showwarning("CRC计算结果", f"{msg}\n❌ CRC值匹配: 否")
        except Exception as e:
            self.logger.log(f"❌ 计算CRC时发生错误: {e}")
            messagebox.showerror("错误", f"计算CRC时发生错误:\n{e}")

    def replace_original(self):
        success = replace_file(
            source_path=self.modified_path,
            dest_path=self.original_path,
            create_backup=self.create_backup.get(),
            ask_confirm=True,
            confirm_message="确定要用修改后的文件替换原始文件吗？\n\n此操作不可逆，建议先备份原始文件！",
            log=self.logger.log,
        )
