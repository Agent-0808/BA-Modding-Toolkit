# i18n.py
import json
import locale
import sys
from functools import reduce, lru_cache
from pathlib import Path
from typing import Any

def get_locale_dir() -> Path:
    """
    获取 locales 目录路径
    优先级：
    1. 打包环境：exe 同级目录下的 locales 文件夹
    2. 开发环境：包内部的 locales 文件夹
    """
    # 检查是否运行在打包环境
    # 如果是打包环境，优先查找 exe 同级目录下的 locales 文件夹
    exe_dir = Path(sys.executable).parent
    external_locales = exe_dir / "locales"
    if external_locales.exists() and external_locales.is_dir():
        return external_locales

    # 2. 如果不是打包环境，或者是开发环境
    # 查找代码包内部的 locales 文件夹
    internal_locales = Path(__file__).parent / "locales"
    return internal_locales

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

def get_default_language() -> str:
    """
    根据系统语言获取默认语言设置
    如果系统语言是中文，使用zh-CN，否则使用debug模式
    """
    system_lang = get_system_language()
    # 如果系统语言是中文，使用zh-CN，否则使用debug模式
    if system_lang and (system_lang.startswith("zh-")):
        return "zh-CN"
    else:
        return "debug"

class I18n:
    def __init__(self, lang: str | None = None, locales_dir: str | None = None):
        self.fallback_lang = "en-US"
        self.lang = lang or get_default_language()
        self.locales_dir = Path(locales_dir) if locales_dir else get_locale_dir()
        self.translations: dict[str, Any] = {}
        self.fallback_translations: dict[str, Any] = {}
        
        self.load_translations()

    def load_translations(self) -> None:
        """
        加载翻译文件
        支持 Debug 模式和 key 级别回退：
        - zh-* 语言：回退到 zh-CN → key
        - 其他语言：回退到 en-US → key
        """
        print(f"Loading locales from: {self.locales_dir}")
        
        if self.lang == "debug":
            self.translations = {}
            self.fallback_translations = {}
            self._get_template.cache_clear()
            print("I18n: Debug mode enabled.")
            return

        if self.lang.startswith("zh-"):
            fallback_code = "zh-CN"
        else:
            fallback_code = "en-US"

        main_path = self.locales_dir / f"{self.lang}.json"
        fallback_path = self.locales_dir / f"{fallback_code}.json"

        main_exists = main_path.exists()
        fallback_exists = fallback_path.exists()

        if not main_exists and not fallback_exists:
            print(f"I18n Warning: Language '{self.lang}' not found, fallback '{fallback_code}' not found either.")
        elif not main_exists and fallback_exists:
            print(f"I18n: Language '{self.lang}' not found, using fallback '{fallback_code}'.")
        elif main_exists:
            print(f"I18n: Loaded language '{self.lang}'.")

        self.translations = self._load_translation_file(main_path)
        self.fallback_translations = self._load_translation_file(fallback_path)

        if not self.translations and not self.fallback_translations:
            print(f"Warning: No translation files found for '{self.lang}' or '{fallback_code}'.")

        self._get_template.cache_clear()

    def _load_translation_file(self, path: Path) -> dict[str, Any]:
        """加载单个翻译文件"""
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Failed to load translations from {path}: {e}")
            return {}

    @lru_cache(maxsize=1024)
    def _get_template(self, key: str) -> str:
        """
        内部方法：查找翻译，支持 key 级别回退
        """
        keys = key.split(".")

        # 在主语言中查找
        main_value = self._get_nested_value(self.translations, keys)
        if main_value is not None:
            return str(main_value)

        # 主语言没有这个 key，去回退语言查找
        fallback_value = self._get_nested_value(self.fallback_translations, keys)
        if fallback_value is not None:
            return str(fallback_value)

        # 都找不到，返回 key 本身
        return key

    def _get_nested_value(self, data: dict[str, Any], keys: list[str]) -> Any:
        """从嵌套字典中获取值"""
        try:
            return reduce(lambda d, k: d[k], keys, data)
        except (KeyError, TypeError):
            return None

    def t(self, _key: str, **kwargs: Any) -> str:
        """
        获取翻译文本，支持参数替换
        用法: t("log.success", msg="更新成功")
        对应的 JSON: { "log": { "success": "成功: {msg}" } }
        """
        template = self._get_template(_key)
        
        # 如果没有传参数，直接返回
        if not kwargs:
            return template
        
        # Debug 模式或键缺失时，返回键名和参数
        if self.lang == "debug" or template == _key:
            return f"{_key}({', '.join(f'{k}={v}' for k, v in kwargs.items())})"
            
        try:
            # 使用 python 标准的 format 方法进行替换
            return template.format(**kwargs)
        except KeyError as e:
            # 如果 JSON 里写了 {name} 但代码没传 name 参数，避免崩溃，返回原始模板或报错信息
            print(f"Warning: Missing format argument {e} for key '{_key}'")
            return template
        except Exception as e:
            print(f"Warning: Formatting error for key '{_key}': {e}")
            return template

    def set_language(self, lang: str) -> None:
        """切换语言并重新加载"""
        if self.lang != lang:
            self.lang = lang
            self.load_translations()

    def get_available_languages(self) -> list[str]:
        """获取可用的语言列表"""
        languages = []
        
        if self.locales_dir.exists():
            for json_file in self.locales_dir.glob("*.json"):
                lang_code = json_file.stem
                languages.append(lang_code)
        
        languages.sort()
        
        if "debug" not in languages:
            languages.append("debug")
        
        return languages

# 创建全局 i18n 实例
i18n_manager = I18n()
t = i18n_manager.t