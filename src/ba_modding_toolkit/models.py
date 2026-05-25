# models.py
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Literal, NamedTuple
from PIL import Image


from UnityPy.enums import ClassIDType as AssetType


# -------- 基础命名元组和类型别名 ---------

class NameTypeKey(NamedTuple):
    """name_type匹配策略所用的键"""
    name: str | None
    type: str

    def __str__(self) -> str:
        return f"[{self.type}] {self.name}"


class ContNameTypeKey(NamedTuple):
    """cont_name_type匹配策略所用的键"""
    container: str | None
    name: str
    type: str

    def __str__(self) -> str:
        return f"[{self.type}] {self.name} @ {self.container}"


AssetKey = str | int | NameTypeKey | ContNameTypeKey

# 资源的具体内容，可以是字节数据、PIL图像或None
AssetContent = bytes | Image.Image | None  

# 补丁，用于描述向Bundle文件进行的资源替换操作
Patch = dict[AssetKey, AssetContent]

# 日志函数类型
LogFunc = Callable[[str], None]  

# 压缩类型
CompressionType = Literal["lzma", "lz4", "original", "none"]  

# 匹配策略类型
MatchStrategy = Literal['path_id', 'name_type', 'cont_name_type']


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

class PatchResult(NamedTuple):
    """封装资源修改操作的结果。"""
    applied_count: int              # 实际执行修改的数量
    skipped_count: int              # 匹配但内容相同跳过的数量
    applied_logs: list[str]         # 修改成功的日志
    unmatched_keys: list[AssetKey]  # 未匹配的资源键
    matched_keys: list[AssetKey]    # 匹配成功的资源键（包括修改和跳过的）
    
    @property
    def matched_count(self) -> int:
        """总匹配数（包括修改和跳过的）"""
        return self.applied_count + self.skipped_count
    
    @property
    def is_success(self) -> bool:
        """是否有资源匹配成功（无论是否实际修改）"""
        return self.matched_count > 0

class FilePair(NamedTuple):
    """core 中处理产生的文件对，包含output和source"""

    output: Path    # 输出文件路径
    source: Path    # 源文件路径

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
