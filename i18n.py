# i18n.py
import json
import locale
from functools import reduce, lru_cache
from pathlib import Path
from typing import Any

def get_system_language() -> str | None:
    """
    获取标准化后的系统语言代码 (如: zh-CN, en-US)
    如果无法检测，默认返回 en-US
    """
    try:
        # 获取系统默认 locale，例如 ('zh_CN', 'UTF-8')
        loc = locale.getdefaultlocale()[0]
        return loc.replace("_", "-")
    except Exception:
        print("Error: Failed to detect system language.")
        return None

class I18n:
    def __init__(self, lang: str | None = None, locales_dir: str = "locales"):
        self.default_lang = "en-US"
        # 如果未指定语言，尝试自动获取系统语言
        self.lang = lang or get_system_language() or self.default_lang
        self.locales_dir = Path(locales_dir)
        self.translations: dict[str, Any] = {}
        
        # 定义回退映射：当 key 对应的语言文件不存在时，尝试 value 对应的语言
        self.fallback_map: dict[str, str] = {
            "zh-TW": "zh-CN",
            "zh-HK": "zh-CN",
            "zh-MO": "zh-CN",
        }
        
        
        self.load_translations()

    def load_translations(self) -> None:
        """
        加载翻译文件
        支持 Debug 模式、自定义回退机制和默认英语回退
        """
        # Debug 模式：不加载任何文件，让 _get_template 直接返回 Key
        if self.lang == "debug":
            self.translations = {}
            self._get_template.cache_clear()
            print("I18n: Debug mode enabled.")
            return

        # 构建查找候选列表：[当前语言, 自定义回退语言, 默认语言]
        candidates = [self.lang]
        if fallback := self.fallback_map.get(self.lang):
            candidates.append(fallback)
        if self.default_lang not in candidates:
            candidates.append(self.default_lang)

        # 按顺序查找存在的语言文件
        selected_path = None
        for code in candidates:
            path = self.locales_dir / f"{code}.json"
            if path.exists():
                selected_path = path
                # 如果实际加载的不是首选语言，可以打印提示
                if code != self.lang:
                    print(f"I18n: '{self.lang}.json' not found, falling back to '{code}'")
                break
        
        if not selected_path:
            print(f"Warning: No translation files found for language '{self.lang}' or fallbacks.")
            self.translations = {}
            self._get_template.cache_clear()
            return

        try:
            self.translations = json.loads(selected_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Failed to load translations from {selected_path}: {e}")
            self.translations = {}
        
        # 清除缓存，注意这里我们要清除的是内部查找方法的缓存
        self._get_template.cache_clear()

    @lru_cache(maxsize=1024)
    def _get_template(self, key: str, **kwargs) -> str:
        """
        内部方法：仅负责查找原始字符串并缓存结果
        """
        # Debug 模式直接返回键名
        if self.lang == "debug":
            if kwargs:
                return f"{key}({', '.join(f'{k}={v}' for k, v in kwargs.items())})"
            return key

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
        # Debug 模式下传入参数信息
        if self.lang == "debug" and kwargs:
            template = self._get_template(key, **kwargs)
        else:
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