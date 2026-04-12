# models.py
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Literal, NamedTuple
from PIL import Image

# 导入 UnityPy 相关类型
from UnityPy.enums import ClassIDType as AssetType
from UnityPy.files import ObjectReader as Obj


# -------- 基础命名元组和类型别名 ---------

class NameTypeKey(NamedTuple):
    name: str | None
    type: str

    def __str__(self) -> str:
        return f"[{self.type}] {self.name}"


class ContNameTypeKey(NamedTuple):
    container: str | None
    name: str
    type: str

    def __str__(self) -> str:
        return f"[{self.type}] {self.name} @ {self.container}"


AssetKey = str | int | NameTypeKey | ContNameTypeKey

# 资源的具体内容，可以是字节数据、PIL图像或None
AssetContent = bytes | Image.Image | None  

# 从对象生成资源键的函数，接收UnityPy对象，返回该资源的键
KeyGeneratorFunc = Callable[[Obj], AssetKey]

# 日志函数类型
LogFunc = Callable[[str], None]  

# 压缩类型
CompressionType = Literal["lzma", "lz4", "original", "none"]  


# -------- 匹配策略 (用于生成 AssetKey) ---------

MATCH_STRATEGIES: dict[str, KeyGeneratorFunc] = {
    # path_id: 使用 Unity 对象的 path_id 作为键，适用于相同版本精确匹配，主要方式
    'path_id': lambda obj: obj.path_id,
    # name_type: 使用 (资源名, 资源类型) 作为键，适用于按名称和类型匹配，在Asset Packing中使用
    'name_type': lambda obj: NameTypeKey(obj.peek_name(), obj.type.name),
    # cont_name_type: 使用 (容器名, 资源名, 资源类型) 作为键，适用于按容器、名称和类型匹配，用于跨版本移植
    'cont_name_type': lambda obj: ContNameTypeKey(obj.container, obj.peek_name(), obj.type.name),
}


# -------- 业务配置 DataClass ---------

@dataclass
class SaveOptions:
    """封装了保存、压缩和CRC修正相关的选项。"""
    perform_crc: bool = True
    extra_bytes: bytes | None = None
    compression: CompressionType = "lzma"


@dataclass
class SpineOptions:
    """封装了Spine版本转换相关的选项。"""
    enabled: bool = False
    converter_path: Path | None = None
    target_version: str | None = None

    def is_valid(self) -> bool:
        """检查Spine转换功能是否已配置并可用。"""
        return (
            self.enabled
            and self.converter_path
            and self.converter_path.exists()
            and self.target_version
            and self.target_version.count(".") == 2
        )

class ReplacementResult(NamedTuple):
    """封装资源替换操作的结果。"""
    replaced_count: int          # 实际执行替换的数量
    skipped_count: int           # 匹配但内容相同跳过的数量
    replaced_logs: list[str]     # 替换成功的日志
    unmatched_keys: list[AssetKey]  # 未匹配的资源键
    
    @property
    def matched_count(self) -> int:
        """总匹配数（包括替换和跳过的）"""
        return self.replaced_count + self.skipped_count
    
    @property
    def is_success(self) -> bool:
        """是否有资源匹配成功（无论是否实际替换）"""
        return self.matched_count > 0

class ParsedFilename(NamedTuple):
    """
    解析后的文件名结构。

    Attributes:
        category: 资源分类 (如 spinecharacters)，可能为 None
        core: 核心名称 (如 ch0808_spr)，必须有值
        res_type: 资源类型 (如 textassets)，可能为 None
        date: 日期字符串 (YYYY-MM-DD)
        crc: CRC32 校验码
        prefix: 用于搜索新版文件的前缀
    """
    category: str | None
    core: str
    res_type: str | None
    date: str
    crc: str
    prefix: str

# -------- 全局游戏业务映射常量 ---------

# 将日服文件名中的类型标识符映射到UnityPy的AssetType名称
JP_FILENAME_TYPE_MAP = {
    "textures": "Texture2D",
    "textassets": "TextAsset",
    "materials": "Material",
    "meshes": "Mesh",
    "animationclip": "AnimationClip",
    "audio": "AudioClip",
    "prefabs": "Prefab",
}

# 可替换的资源类型白名单
REPLACEABLE_ASSET_TYPES: set[AssetType] = {
    # 纹理类
    AssetType.Texture2D, AssetType.Texture3D, AssetType.Cubemap,
    AssetType.RenderTexture, AssetType.CustomRenderTexture, AssetType.Sprite, AssetType.SpriteAtlas,

    # 文本和脚本类
    AssetType.TextAsset, AssetType.MonoBehaviour, AssetType.MonoScript,

    # 音频类
    AssetType.AudioClip,

    # 网格和材质类
    AssetType.Mesh, AssetType.Material, AssetType.Shader,

    # 动画类
    AssetType.AnimationClip, AssetType.Animator, AssetType.AnimatorController,
    AssetType.RuntimeAnimatorController, AssetType.Avatar, AssetType.AvatarMask,

    # 字体类
    AssetType.Font,

    # 视频类
    AssetType.VideoClip,

    # 地形类
    AssetType.TerrainData,

    # 其他资源类
    AssetType.PhysicMaterial, AssetType.ComputeShader, AssetType.Flare, AssetType.LensFlare,
}
