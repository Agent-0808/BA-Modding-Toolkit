# ui/dialogs.py

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

from i18n import t
from .components import Theme, UIComponents
from .utils import select_file

class SettingsDialog(tk.Toplevel):
    def __init__(self, master, app_instance):
        super().__init__(master)
        self.app = app_instance # 保存主应用的引用

        self.title(t("ui.settings.title"))
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
            placeholder_text=t("ui.label.resource_dir")
        )
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5), ipady=3)

        select_btn = UIComponents.create_button(entry_button_container, t("action.select_short"), self.app.select_game_resource_directory, bg_color=Theme.BUTTON_PRIMARY_BG, style="compact")
        select_btn.pack(side=tk.LEFT, padx=(0, 5))
        open_btn = UIComponents.create_button(entry_button_container, t("action.open_short"), self.app.open_game_resource_in_explorer, bg_color=Theme.BUTTON_SECONDARY_BG, style="compact")
        open_btn.pack(side=tk.LEFT)

        self.auto_detect_checkbox = tk.Checkbutton(
            self.game_dir_frame, 
            text=t("option.auto_detect_subdirs"),
            variable=self.app.auto_detect_subdirs_var,
            command=self._on_auto_detect_toggle,
            font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL, selectcolor=Theme.INPUT_BG
        )
        self.auto_detect_checkbox.pack(anchor='w', pady=(5, 0))
        # --- 游戏资源目录UI结束 ---

        UIComponents.create_directory_path_entry(
            container, t("ui.label.output_dir"), self.app.output_dir_var,
            self.app.select_output_directory, self.app.open_output_dir_in_explorer,
            placeholder_text=t("ui.label.output_dir")
        )
        
        # 应用设置
        app_settings_frame = tk.LabelFrame(container, text=t("ui.settings.group_app"), font=Theme.FRAME_FONT, fg=Theme.TEXT_TITLE, bg=Theme.FRAME_BG, padx=15, pady=5)
        app_settings_frame.pack(fill=tk.X, pady=(5, 0))
        
        # 语言选择
        language_frame = tk.Frame(app_settings_frame, bg=Theme.FRAME_BG)
        language_frame.pack(fill=tk.X)
        
        language_label = tk.Label(language_frame, text=t("ui.label.language"), font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL)
        language_label.pack(side=tk.LEFT, padx=(0, 10))
        
        language_combo = UIComponents.create_combobox(language_frame, textvariable=self.app.language_var, values=["zh-CN", "debug"], width=10)
        language_combo.pack(side=tk.LEFT)
        language_combo.bind("<<ComboboxSelected>>", self._on_language_changed)
        
        # 选项设置
        global_options_frame = tk.LabelFrame(container, text=t("ui.settings.group_global"), font=Theme.FRAME_FONT, fg=Theme.TEXT_TITLE, bg=Theme.FRAME_BG, padx=5, pady=5)
        global_options_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.padding_checkbox = tk.Checkbutton(global_options_frame, text=t("option.padding"), variable=self.app.enable_padding_var, font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL, selectcolor=Theme.INPUT_BG)
        crc_checkbox = tk.Checkbutton(global_options_frame, text=t("option.crc_correction"), variable=self.app.enable_crc_correction_var, font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL, selectcolor=Theme.INPUT_BG, command=self.toggle_padding_checkbox_state)
        backup_checkbox = tk.Checkbutton(global_options_frame, text=t("option.backup"), variable=self.app.create_backup_var, font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL, selectcolor=Theme.INPUT_BG)

        # 压缩方式下拉框
        compression_frame = tk.Frame(global_options_frame, bg=Theme.FRAME_BG)
        compression_label = tk.Label(compression_frame, text=t("ui.label.compression_method"), font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL)
        compression_combo = UIComponents.create_combobox(compression_frame, textvariable=self.app.compression_method_var, values=["lzma", "lz4", "original", "none"], width=10)

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
        asset_replace_frame = tk.LabelFrame(container, text=t("ui.settings.group_assets"), font=Theme.FRAME_FONT, fg=Theme.TEXT_TITLE, bg=Theme.FRAME_BG, padx=15, pady=5)
        asset_replace_frame.pack(fill=tk.X, pady=8)
        
        asset_checkbox_container = tk.Frame(asset_replace_frame, bg=Theme.FRAME_BG)
        asset_checkbox_container.pack(fill=tk.X)
        
        tk.Checkbutton(asset_checkbox_container, text=t("option.replace_all"), variable=self.app.replace_all_var, font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL, selectcolor=Theme.INPUT_BG).pack(side=tk.LEFT)
        tk.Checkbutton(asset_checkbox_container, text=t("option.replace_texture"), variable=self.app.replace_texture2d_var, font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL, selectcolor=Theme.INPUT_BG).pack(side=tk.LEFT, padx=(0, 20))
        tk.Checkbutton(asset_checkbox_container, text=t("option.replace_textasset"), variable=self.app.replace_textasset_var, font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL, selectcolor=Theme.INPUT_BG).pack(side=tk.LEFT, padx=(0, 20))
        tk.Checkbutton(asset_checkbox_container, text=t("option.replace_mesh"), variable=self.app.replace_mesh_var, font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL, selectcolor=Theme.INPUT_BG).pack(side=tk.LEFT, padx=(0, 20))
        
        # Spine 转换器设置
        spine_frame = tk.LabelFrame(container, text=t("ui.settings.group_spine"), font=Theme.FRAME_FONT, fg=Theme.TEXT_TITLE, bg=Theme.FRAME_BG, padx=15, pady=5)
        spine_frame.pack(fill=tk.X, pady=(5, 0))
        
        # Spine 转换选项
        spine_options_frame = tk.Frame(spine_frame, bg=Theme.FRAME_BG)
        spine_options_frame.pack(fill=tk.X)
        
        spine_conversion_checkbox = tk.Checkbutton(spine_options_frame, text=t("option.spine_conversion"), variable=self.app.enable_spine_conversion_var, font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL, selectcolor=Theme.INPUT_BG)
        spine_conversion_checkbox.pack(side=tk.LEFT, padx=(0, 10))
        
        # 目标版本输入框
        spine_version_label = tk.Label(spine_options_frame, text=t("ui.label.target_version"), font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL)
        spine_version_label.pack(side=tk.LEFT, padx=(0, 5))
        
        spine_version_entry = UIComponents.create_textbox_entry(
            spine_options_frame, 
            textvariable=self.app.target_spine_version_var,
            placeholder_text=t("ui.label.spine_version")
        )
        spine_version_entry.pack(side=tk.LEFT)

        # Spine 转换器路径设置
        UIComponents.create_file_path_entry(
            spine_frame, t("ui.label.skel_converter_path"), self.app.spine_converter_path_var,
            self.select_spine_converter_path
        )
        
        # Spine 降级工具路径设置
        UIComponents.create_file_path_entry(
            spine_frame, t("ui.label.atlas_downgrade_path"), self.app.atlas_downgrade_path_var,
            self.select_atlas_downgrade_path
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
        
        save_button = UIComponents.create_button(config_buttons_frame, t("common.save"), self.app.save_current_config, bg_color=Theme.BUTTON_SUCCESS_BG)
        save_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        load_button = UIComponents.create_button(config_buttons_frame, t("common.load"), self.load_config, bg_color=Theme.BUTTON_WARNING_BG)
        load_button.grid(row=0, column=1, sticky="ew", padx=5)
        
        reset_button = UIComponents.create_button(config_buttons_frame, t("common.reset"), self.reset_to_default, bg_color=Theme.BUTTON_DANGER_BG)
        reset_button.grid(row=0, column=2, sticky="ew", padx=(5, 0))

    def _on_auto_detect_toggle(self):
        """当自动检测复选框状态改变时，更新UI"""
        if self.app.auto_detect_subdirs_var.get():
            self.game_dir_frame.config(text=t("ui.label.game_root_dir"))
        else:
            self.game_dir_frame.config(text=t("ui.label.custom_resource_dir"))

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
            self.app.logger.log(t("log.status.ready"))
            messagebox.showinfo(t("common.success"), t("message.config.loaded"))
            # 更新UI状态
            self.toggle_padding_checkbox_state()
            self._on_auto_detect_toggle()
        else:
            self.app.logger.log(t("log.config.load_failed"))
            messagebox.showerror(t("common.error"), t("message.config.load_failed"))
    
    def reset_to_default(self):
        """重置为默认设置"""
        if messagebox.askyesno(t("common.tip"), t("message.confirm_reset_settings")):
            # 使用统一的默认值设置方法
            self.app._set_default_values()
            
            # 更新UI状态
            self.toggle_padding_checkbox_state()
            self._on_auto_detect_toggle()
            
            self.app.logger.log(t("log.config.reset"))
    
    def select_spine_converter_path(self):
        """选择Spine转换器路径"""
        select_file(
            title=t("ui.dialog.select", type=t("file_type.skel_converter")),
            filetypes=[(t("file_type.executable"), "*.exe"), (t("file_type.all_files"), "*.*")],
            callback=lambda path: (
                self.app.spine_converter_path_var.set(str(path)),
                self.app.logger.log(t("log.spine.skel_converter_set", path=path))
            ),
            logger=self.app.logger.log
        )

    def select_atlas_downgrade_path(self):
        """选择SpineAtlasDowngrade.exe路径"""
        select_file(
            title=t("ui.dialog.select", type=t("file_type.atlas_downgrade")),
            filetypes=[(t("file_type.executable"), "*.exe"), (t("file_type.all_files"), "*.*")],
            callback=lambda path: (
                self.app.atlas_downgrade_path_var.set(str(path)),
                self.app.logger.log(t("log.spine.atlas_downgrade_set", path=path))
            ),
            logger=self.app.logger.log
        )

    def _on_language_changed(self, event=None):
        """语言选择改变时的处理"""
        selected_language = self.app.language_var.get()
        self.app.logger.log(f"语言已切换为: {selected_language}")
        
        # 弹出提示对话框
        messagebox.showinfo(
            t("common.tip"),
            t("message.config.language_changed"),
            parent=self
        )