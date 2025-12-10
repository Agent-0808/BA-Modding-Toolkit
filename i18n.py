# i18n.py
import json
from functools import reduce, lru_cache
from pathlib import Path
from typing import Any

class I18n:
    def __init__(self, lang: str = "zh-CN", locales_dir: str = "locales"):
        self.lang = lang
        self.locales_dir = Path(locales_dir)
        self.translations: dict[str, Any] = {}
        self.load_translations()

    def load_translations(self) -> None:
        """加载当前语言的 JSON 文件"""
        file_path = self.locales_dir / f"{self.lang}.json"
        
        if not file_path.exists() and self.lang != "en-US":
             file_path = self.locales_dir / "en-US.json"

        try:
            self.translations = json.loads(file_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Warning: Failed to load translations from {file_path}: {e}")
            self.translations = {}
        
        # 清除缓存，注意这里我们要清除的是内部查找方法的缓存
        self._get_template.cache_clear()

    @lru_cache(maxsize=1024)
    def _get_template(self, key: str) -> str:
        """
        内部方法：仅负责查找原始字符串并缓存结果
        """
        keys = key.split(".")
        try:
            value = reduce(lambda d, k: d[k], keys, self.translations)
            return str(value)
        except (KeyError, TypeError):
            # 找不到翻译时返回 key 本身
            return key

    def t(self, key: str, **kwargs: Any) -> str:
        """
        获取翻译文本，支持参数替换
        用法: t("log.success", msg="更新成功")
        对应的 JSON: { "log": { "success": "成功: {msg}" } }
        """
        template = self._get_template(key)
        
        # 如果没有传参数，直接返回
        if not kwargs:
            return template
            
        try:
            # 使用 python 标准的 format 方法进行替换
            return template.format(**kwargs)
        except KeyError as e:
            # 如果 JSON 里写了 {name} 但代码没传 name 参数，避免崩溃，返回原始模板或报错信息
            print(f"Warning: Missing format argument {e} for key '{key}'")
            return template
        except Exception as e:
            print(f"Warning: Formatting error for key '{key}': {e}")
            return template

    def set_language(self, lang: str) -> None:
        """切换语言并重新加载"""
        if self.lang != lang:
            self.lang = lang
            self.load_translations()

# 创建全局 i18n 实例
i18n_manager = I18n()
t = i18n_manager.t