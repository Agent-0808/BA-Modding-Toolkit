# ui/dialogs.py

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

from .components import Theme, UIComponents

class SettingsDialog(tk.Toplevel):
    def __init__(self, master, app_instance):
        super().__init__(master)
        self.app = app_instance # 保存主应用的引用

        self.title("高级设置")
        self.geometry("500x700")
        self.configure(bg=Theme.WINDOW_BG)
        self.transient(master) # 绑定到主窗口

        # --- 将原有的全局设置UI搬到这里 ---
        container = tk.Frame(self, bg=Theme.WINDOW_BG, padx=15, pady=15)
        container.pack(fill=tk.BOTH, expand=True)

        # TODO: 3种Preset

        # TODO: 去掉auto_detect_checkbox，全部启用

        # --- 手动创建游戏资源目录UI，以实现动态标题 ---
        self.game_dir_frame = tk.LabelFrame(container, text="", font=Theme.FRAME_FONT, fg=Theme.TEXT_TITLE, bg=Theme.FRAME_BG, padx=15, pady=8)
        self.game_dir_frame.pack(fill=tk.X, pady=5)

        # 内部容器，用于放置输入框和按钮
        entry_button_container = tk.Frame(self.game_dir_frame, bg=Theme.FRAME_BG)
        entry_button_container.pack(fill=tk.X)

        entry = UIComponents.create_textbox_entry(
            entry_button_container, 
            textvariable=self.app.game_resource_dir_var,
            placeholder_text="选择游戏资源目录"
        )
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5), ipady=3)

        select_btn = UIComponents.create_button(entry_button_container, "选", self.app.select_game_resource_directory, bg_color=Theme.BUTTON_PRIMARY_BG, width=3, style="compact")
        select_btn.pack(side=tk.LEFT, padx=(0, 5))
        open_btn = UIComponents.create_button(entry_button_container, "开", self.app.open_game_resource_in_explorer, bg_color=Theme.BUTTON_SECONDARY_BG, width=3, style="compact")
        open_btn.pack(side=tk.LEFT)

        self.auto_detect_checkbox = tk.Checkbutton(
            self.game_dir_frame, 
            text="自动检测标准子目录 (GameData/Preload)",
            variable=self.app.auto_detect_subdirs_var,
            command=self._on_auto_detect_toggle,
            font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL, selectcolor=Theme.INPUT_BG
        )
        self.auto_detect_checkbox.pack(anchor='w', pady=(5, 0))
        # --- 游戏资源目录UI结束 ---

        UIComponents.create_directory_path_entry(
            container, "输出目录", self.app.output_dir_var,
            self.app.select_output_directory, self.app.open_output_dir_in_explorer,
            placeholder_text="选择输出目录"
        )
        
        # 选项设置
        global_options_frame = tk.LabelFrame(container, text="全局选项", font=Theme.FRAME_FONT, fg=Theme.TEXT_TITLE, bg=Theme.FRAME_BG, padx=5, pady=5)
        global_options_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.padding_checkbox = tk.Checkbutton(global_options_frame, text="添加私货", variable=self.app.enable_padding_var, font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL, selectcolor=Theme.INPUT_BG)
        crc_checkbox = tk.Checkbutton(global_options_frame, text="CRC修正", variable=self.app.enable_crc_correction_var, font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL, selectcolor=Theme.INPUT_BG, command=self.toggle_padding_checkbox_state)
        backup_checkbox = tk.Checkbutton(global_options_frame, text="创建备份", variable=self.app.create_backup_var, font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL, selectcolor=Theme.INPUT_BG)

        # 压缩方式下拉框
        compression_frame = tk.Frame(global_options_frame, bg=Theme.FRAME_BG)
        compression_label = tk.Label(compression_frame, text="压缩方式", font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL)
        compression_combo = ttk.Combobox(compression_frame, textvariable=self.app.compression_method_var, values=["lzma", "lz4", "original", "none"], state="readonly", font=Theme.INPUT_FONT, width=10)

        # 布局 - 使用统一的grid布局确保高度对齐
        crc_checkbox.grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.padding_checkbox.grid(row=0, column=1, sticky="w", padx=(0, 5))
        backup_checkbox.grid(row=0, column=2, sticky="w", padx=(0, 5))
        
        compression_frame.grid(row=0, column=3, sticky="w", padx=(0, 5))
        compression_label.pack(side=tk.LEFT)
        compression_combo.pack(side=tk.LEFT)
        
        # 设置行权重确保垂直对齐
        global_options_frame.rowconfigure(0, weight=1)
        
        # 资源替换类型选项
        asset_replace_frame = tk.LabelFrame(container, text="替换资源类型", font=Theme.FRAME_FONT, fg=Theme.TEXT_TITLE, bg=Theme.FRAME_BG, padx=15, pady=5)
        asset_replace_frame.pack(fill=tk.X, pady=8)
        
        asset_checkbox_container = tk.Frame(asset_replace_frame, bg=Theme.FRAME_BG)
        asset_checkbox_container.pack(fill=tk.X)
        
        tk.Checkbutton(asset_checkbox_container, text="ALL", variable=self.app.replace_all_var, font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL, selectcolor=Theme.INPUT_BG).pack(side=tk.LEFT)
        tk.Checkbutton(asset_checkbox_container, text="Texture2D", variable=self.app.replace_texture2d_var, font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL, selectcolor=Theme.INPUT_BG).pack(side=tk.LEFT, padx=(0, 20))
        tk.Checkbutton(asset_checkbox_container, text="TextAsset", variable=self.app.replace_textasset_var, font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL, selectcolor=Theme.INPUT_BG).pack(side=tk.LEFT, padx=(0, 20))
        tk.Checkbutton(asset_checkbox_container, text="Mesh", variable=self.app.replace_mesh_var, font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL, selectcolor=Theme.INPUT_BG).pack(side=tk.LEFT, padx=(0, 20))
        
        # Spine 转换器设置
        spine_frame = tk.LabelFrame(container, text="Spine 转换器设置", font=Theme.FRAME_FONT, fg=Theme.TEXT_TITLE, bg=Theme.FRAME_BG, padx=15, pady=12)
        spine_frame.pack(fill=tk.X, pady=(15, 0))
        
        # Spine 转换选项
        spine_options_frame = tk.Frame(spine_frame, bg=Theme.FRAME_BG)
        spine_options_frame.pack(fill=tk.X)
        
        spine_conversion_checkbox = tk.Checkbutton(spine_options_frame, text="启用 Spine 转换", variable=self.app.enable_spine_conversion_var, font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL, selectcolor=Theme.INPUT_BG)
        spine_conversion_checkbox.pack(side=tk.LEFT, padx=(0, 10))
        
        # 目标版本输入框
        spine_version_label = tk.Label(spine_options_frame, text="目标版本:", font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL)
        spine_version_label.pack(side=tk.LEFT, padx=(0, 5))
        
        spine_version_entry = UIComponents.create_textbox_entry(
            spine_options_frame, 
            textvariable=self.app.target_spine_version_var,
            placeholder_text="目标版本",
            width=10
        )
        spine_version_entry.pack(side=tk.LEFT)

        # Spine 转换器路径设置
        UIComponents.create_file_path_entry(
            spine_frame, "SpineSkeletonDataConverter.exe 路径", self.app.spine_converter_path_var,
            self.select_spine_converter_path
        )
        
        # Spine 降级工具路径设置
        UIComponents.create_file_path_entry(
            spine_frame, "SpineAtlasDowngrade.exe 路径", self.app.atlas_downgrade_path_var,
            self.app.select_atlas_downgrade_path
        )

        # 初始化所有动态UI的状态
        self.toggle_padding_checkbox_state()
        self._on_auto_detect_toggle()
        
        # 添加配置操作按钮
        config_buttons_frame = tk.Frame(container, bg=Theme.WINDOW_BG)
        config_buttons_frame.pack(fill=tk.X, pady=(15, 0))
        
        # 配置网格布局，让三个按钮均匀分布
        config_buttons_frame.columnconfigure(0, weight=1)
        config_buttons_frame.columnconfigure(1, weight=1)
        config_buttons_frame.columnconfigure(2, weight=1)
        
        save_button = UIComponents.create_button(config_buttons_frame, "Save", self.app.save_current_config, bg_color=Theme.BUTTON_SUCCESS_BG)
        save_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        load_button = UIComponents.create_button(config_buttons_frame, "Load", self.load_config, bg_color=Theme.BUTTON_WARNING_BG)
        load_button.grid(row=0, column=1, sticky="ew", padx=5)
        
        reset_button = UIComponents.create_button(config_buttons_frame, "Default", self.reset_to_default, bg_color=Theme.BUTTON_DANGER_BG)
        reset_button.grid(row=0, column=2, sticky="ew", padx=(5, 0))

    def _on_auto_detect_toggle(self):
        """当自动检测复选框状态改变时，更新UI"""
        if self.app.auto_detect_subdirs_var.get():
            self.game_dir_frame.config(text="游戏根目录")
        else:
            self.game_dir_frame.config(text="自定义资源目录")

    def toggle_padding_checkbox_state(self):
        """根据CRC修正复选框的状态，启用或禁用添加私货复选框"""
        if self.app.enable_crc_correction_var.get():
            self.padding_checkbox.config(state=tk.NORMAL)
        else:
            self.app.enable_padding_var.set(False)
            self.padding_checkbox.config(state=tk.DISABLED)
    
    def load_config(self):
        """加载配置文件并更新UI"""
        if self.app.config_manager.load_config(self.app):
            self.app.logger.log("配置加载成功")
            messagebox.showinfo("成功", "配置已从 config.ini 加载")
            # 更新UI状态
            self.toggle_padding_checkbox_state()
            self._on_auto_detect_toggle()
        else:
            self.app.logger.log("配置加载失败")
            messagebox.showerror("错误", "配置加载失败，请检查配置文件是否存在")
    
    def reset_to_default(self):
        """重置为默认设置"""
        if messagebox.askyesno("确认", "确定要重置为默认设置吗？"):
            # 使用统一的默认值设置方法
            self.app._set_default_values()
            
            # 更新UI状态
            self.toggle_padding_checkbox_state()
            self._on_auto_detect_toggle()
            
            self.app.logger.log("已重置为默认设置")
    
    def select_spine_converter_path(self):
        """选择Spine转换器路径"""
        try:
            current_path = Path(self.app.spine_converter_path_var.get())
            if not current_path.exists():
                current_path = Path.home()
            
            selected_file = filedialog.askopenfilename(
                title="选择 Spine 转换器程序",
                initialdir=str(current_path.parent) if current_path.parent.exists() else str(current_path),
                filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")]
            )
            
            if selected_file:
                self.app.spine_converter_path_var.set(str(Path(selected_file)))
                self.app.logger.log(f"已设置 Spine 转换器路径: {selected_file}")
        except Exception as e:
            messagebox.showerror("错误", f"选择 Spine 转换器路径时发生错误:\n{e}")