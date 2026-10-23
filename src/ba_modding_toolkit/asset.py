# asset.py

import re
from dataclasses import dataclass

from UnityPy.environment import Environment as Env
from UnityPy.files import File as UnityFile

from .i18n import t
from .models import (
    AssetContent, AssetType, AnimCheckOptions, LogFunc,
    RawAssetBytes, SkelConvertOptions, SkelVersionConflict,
)
from .spine import SkelConverter, check_skel_animation_diff
from .utils import no_log


# -------- 提取/应用上下文 --------

@dataclass
class ExtractContext:
    """提取补丁内容的上下文"""
    env_file: UnityFile                       # 来源 bundle 的内部文件（收集流附属用）
    spine_options: SkelConvertOptions | None  # Spine 版本转换选项
    log: LogFunc


@dataclass
class ApplyContext:
    """应用补丁内容的上下文"""
    env: Env                                        # 目标 bundle 环境（companion 写入用）
    anim_check: AnimCheckOptions | None             # skel 动画差异检测选项
    anim_diffs: dict[str, list[str]]                # 动画差异累计输出（原地更新）
    log: LogFunc


# -------- 流式引用辅助（.resS/.resource） --------

# 对象序列化数据中的流式引用 basename（m_StreamData.path / m_Resource.m_Source，如 CAB-xxx.resS）
STREAM_REF_PATTERN = re.compile(rb"[A-Za-z0-9_\-]+\.(?:resS|resource)")

# 流引用完整路径前缀 archive:/<SerializedFile名>/，<SF名> 为包含该对象的内部 SerializedFile 名
STREAM_REF_PREFIX_PATTERN = re.compile(rb"archive:/([A-Za-z0-9_\-]+)/(?=[A-Za-z0-9_\-]+\.(?:resS|resource))")


def find_stream_refs(data: bytes) -> set[str]:
    """提取序列化数据中引用的附属流文件名（.resS/.resource）"""
    return {m.decode() for m in STREAM_REF_PATTERN.findall(data)}


def rewrite_stream_ref_prefixes(data: bytes, target_cab: str, log: LogFunc = no_log) -> bytes:
    """把流引用路径中的 SerializedFile 名段改写为目标 bundle 的 SF 名

    'archive:/<SF名>/<resS名>' 的 <SF名> 必须与目标 bundle 的 SerializedFile 名一致，
    游戏运行时才能解析（raw 替换内容残留源 bundle 的 SF 名，halo 等流式资源在游戏内不可见；
    UnityPy 按 basename 兜底解析，因此仅靠 UnityPy 层测试不会暴露此问题）。
    源/目标 SF 名均为 32 位 hex（等长），直接字节替换不影响序列化布局；
    长度不一致时保留原值并告警（回退 basename 解析）。
    """
    dst = target_cab.encode()
    result = data
    for src in {m.group(1) for m in STREAM_REF_PREFIX_PATTERN.finditer(data)}:
        if src == dst:
            continue
        if len(src) != len(dst):
            log(f'  > ⚠️ {t("log.stream_prefix_skip", src=src.decode(), dst=target_cab)}')
            continue
        result = result.replace(b"archive:/" + src + b"/", b"archive:/" + dst + b"/")
    return result


def collect_stream_companions(raw: bytes, env_file: UnityFile) -> dict[str, bytes] | None:
    """按 raw 内容中的引用 basename 从 bundle 内部文件收集附属流文件

    引用藏在对象 raw 字节内而非序列化引用表，必须按内容匹配收集，
    不能按 bundle 初始文件列表快照（二次提取需携带历史 companion）。

    Returns:
        {basename: 字节}；引用了 bundle 内不存在的文件时返回 None（悬空引用）
    """
    refs = find_stream_refs(raw)
    if not refs:
        return {}
    files = {name: f for name, f in env_file.files.items() if not hasattr(f, "objects")}
    companions: dict[str, bytes] = {}
    for ref in refs:
        entry = files.get(ref)
        if entry is None:
            return None
        companions[ref] = entry.bytes
    return companions


def install_raw_content(content: RawAssetBytes, env: Env, log: LogFunc) -> RawAssetBytes:
    """把 raw 替换内容安装进目标 bundle：写入 companion 附属流文件并改写流引用前缀

    - companion：使内嵌的 .resS/.resource 引用在目标 bundle 内闭合。
      约束：多份 .resS 并存是设计要求（目标自己的与各代 companion 的分别服务不同对象）；
      任何"清理未使用条目"优化不得将无序列化引用的 .resS 当孤儿删除
      引用内嵌于对象 raw 字节，常规引用分析不可见，误删会破坏已分发的 mod。
    - 前缀改写：流引用路径 archive:/<SF名>/ 的 <SF名> 段必须匹配本 bundle，否则游戏运行时无法解析。
    """
    for companion_name, companion_bytes in content.companions.items():
        if companion_name in env.file.files:
            log(f'  > ⏭️ {t("log.replace_companion_exists", name=companion_name)}')
        else:
            env.file.get_writeable_cab(companion_name).write(companion_bytes)
    sf_name = next(n for n, f in env.file.files.items() if hasattr(f, "objects"))
    rewritten = rewrite_stream_ref_prefixes(content, sf_name, log)
    if rewritten != content:
        return RawAssetBytes(rewritten, content.companions)
    return content


# -------- 类型分发 --------

def extract_asset(obj, ctx: ExtractContext) -> tuple[AssetContent | None, list[SkelVersionConflict]]:
    """按资产类型提取单个对象的补丁内容

    - Texture2D：解码为 PIL 图像
    - TextAsset：m_Script 字节；.skel 走 Spine 版本转换
    - 其余类型：raw 整对象字节（携带流附属 companion）

    Returns:
        (补丁内容, skel 版本冲突列表)；内容为 None 表示无可提取内容（跳过）
    """
    data = obj.read()
    if not getattr(data, "m_Name", None):
        return None, []
    resource_name = data.m_Name

    if obj.type == AssetType.Texture2D:
        content: AssetContent = data.image
        return content, []

    if obj.type == AssetType.TextAsset:
        asset_bytes = data.m_Script.encode("utf-8", "surrogateescape")
        if resource_name.lower().endswith('.skel'):
            content, conflict = SkelConverter.ensure_version(
                skel_bytes=asset_bytes,
                resource_name=resource_name,
                options=ctx.spine_options,
                log=ctx.log
            )
            if conflict:
                return None, [conflict]
            return content, []
        content: AssetContent = asset_bytes
        return content, []

    # raw 类型（AnimationClip/Mesh 等）：整对象字节
    raw = obj.get_raw_data()
    companions = collect_stream_companions(raw, ctx.env_file)
    if companions is None:
        # 流引用悬空（如历史版本 raw 替换遗留的坏数据）：
        # 替换会把坏引用带进目标导致资源损坏，拒绝提取该对象
        ctx.log(f"  > ⚠️ {t('log.extractor.stream_ref_dangling', name=resource_name)}")
        return None, []
    # 有流引用时附带 companion 随 patch 走，apply 侧写入目标 bundle
    content: AssetContent = RawAssetBytes(raw, companions) if companions else raw
    return content, []


def apply_asset(obj, content: AssetContent, ctx: ApplyContext) -> bool:
    """把补丁内容应用到目标对象；返回 False 表示内容相同被跳过

    raw dump 内容（RawAssetBytes）：原样替换整个对象的序列化数据，优先于类型特定分支。
    """
    data = obj.read()
    resource_name = data.m_Name

    if isinstance(content, RawAssetBytes):
        if obj.get_raw_data() == content:
            return False
        obj.set_raw_data(install_raw_content(content, ctx.env, ctx.log))
        return True

    if obj.type == AssetType.Texture2D:
        new_image = content
        if (data.image.mode == new_image.mode
                and data.image.size == new_image.size
                and data.image.tobytes() == new_image.tobytes()):
            return False
        data.image = new_image
        data.save()
        return True

    if obj.type == AssetType.TextAsset:
        content: bytes
        target_bytes = data.m_Script.encode("utf-8", "surrogateescape")

        if target_bytes == content:
            return False

        # 就地检测动画差异
        if ctx.anim_check and ctx.anim_check.is_valid() and resource_name.lower().endswith('.skel'):
            ctx.log(f"  🔍 {t('log.spine.anim_check_comparing', name=resource_name)}")
            missing_anims = check_skel_animation_diff(
                source_skel=content,
                target_skel=target_bytes,
                viewer_path=ctx.anim_check.viewer_path,
                log=ctx.log
            )
            if missing_anims:
                ctx.anim_diffs[resource_name] = missing_anims
                ctx.log(f"  ⚠️ {t('log.spine.anim_check_new_animations', name=resource_name, animations=', '.join(missing_anims))}")
            else:
                ctx.log(f"  ✓ {t('log.spine.anim_check_no_diff', name=resource_name)}")

        data.m_Script = content.decode("utf-8", "surrogateescape")
        data.save()
        return True

    # raw 类型（AnimationClip/Mesh 等）：内容相同则跳过，避免无效重存
    if obj.get_raw_data() == content:
        return False
    obj.set_raw_data(content)
    return True
