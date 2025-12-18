# processing.py

import UnityPy
import os
import traceback
from pathlib import Path
from PIL import Image
import shutil
import re
import tempfile
import subprocess
from dataclasses import dataclass
from typing import Callable, Any, Literal

from i18n import t
from utils import CRCUtils, no_log, get_skel_version

# -------- 类型别名 ---------

"""
AssetKey 表示资源的唯一标识符，在不同的流程中可以使用不同的键
    str 类型 表示资源名称，在资源打包工具中使用
    int 类型 表示 path_id
    tuple[str, str] 类型 表示 (名称, 类型) 元组
"""
AssetKey = str | int | tuple[str, str]

# 资源的具体内容，可以是字节数据、PIL图像或None
AssetContent = bytes | Image.Image | None  

# 从对象生成资源键的函数，接收UnityPy对象和一个额外参数，返回该资源的键
KeyGeneratorFunc = Callable[[UnityPy.classes.Object, Any], AssetKey]

# 日志函数类型
LogFunc = Callable[[str], None]  

# 压缩类型
CompressionType = Literal["lzma", "lz4", "original", "none"]  

@dataclass
class SaveOptions:
    """封装了保存、压缩和CRC修正相关的选项。"""
    perform_crc: bool = True
    enable_padding: bool = False
    compression: CompressionType = "lzma"

@dataclass
class SpineOptions:
    """封装了Spine版本更新相关的选项。"""
    enabled: bool = False
    converter_path: Path | None = None
    target_version: str | None = None

    def is_enabled(self) -> bool:
        """检查Spine升级功能是否已配置并可用。"""
        return (
            self.enabled
            and self.converter_path
            and self.converter_path.exists()
            and self.target_version
            and self.target_version.count(".") == 2
        )

@dataclass
class SpineDowngradeOptions:
    """封装了Spine版本降级相关的选项。"""
    enabled: bool = False
    skel_converter_path: Path | None = None
    atlas_converter_path: Path | None = None
    target_version: str = "3.8.75"

    def is_valid(self) -> bool:
        """检查Spine降级功能是否已配置并可用。"""
        return (
            self.enabled
            and self.skel_converter_path is not None
            and self.skel_converter_path.exists()
            and self.atlas_converter_path is not None
            and self.atlas_converter_path.exists()
            and self.target_version
            and self.target_version.count(".") == 2
        )

# ====== 读取与保存相关 ======

def load_bundle(
    bundle_path: Path,
    log: LogFunc = no_log
) -> UnityPy.Environment | None:
    """
    尝试加载一个 Unity bundle 文件。
    如果直接加载失败，会尝试移除末尾的几个字节后再次加载。
    """

    # 1. 尝试直接加载
    try:
        env = UnityPy.load(str(bundle_path))
        return env
    except Exception as e:
        pass

    # 如果直接加载失败，读取文件内容到内存
    try:
        with open(bundle_path, "rb") as f:
            data = f.read()
    except Exception as e:
        log(f'  ❌ {t("log.file.read_in_memory_failed", name=bundle_path.name, error=e)}')
        return None

    # 定义加载策略：字节移除数量
    bytes_to_remove = [4, 8, 12]

    # 2. 依次尝试不同的加载策略
    for bytes_num in bytes_to_remove:
        if len(data) > bytes_num:
            try:
                trimmed_data = data[:-bytes_num]
                env = UnityPy.load(trimmed_data)
                return env
            except Exception as e:
                pass

    log(f'❌ {t("log.file.load_failed", path=bundle_path)}')
    return None

def create_backup(
    original_path: Path,
    backup_mode: str = "default",
    log: LogFunc = no_log,
) -> bool:
    """
    创建原始文件的备份
    backup_mode: "default" - 在原文件后缀后添加.bak
                 "b2b" - 重命名为orig_(原名)
    """
    try:
        if backup_mode == "b2b":
            backup_path = original_path.with_name(f"orig_{original_path.name}")
        else:
            backup_path = original_path.with_suffix(original_path.suffix + '.bak')

        shutil.copy2(original_path, backup_path)
        return True
    except Exception as e:
        log(f'❌ {t("log.file.backup_failed", error=e)}')
        return False

def save_bundle(
    env: UnityPy.Environment,
    output_path: Path,
    compression: CompressionType = "lzma",
    log: LogFunc = no_log,
) -> bool:
    """
    将修改后的 Unity bundle 保存到指定路径。
    """
    try:
        bundle_data = compress_bundle(env, compression, log)
        with open(output_path, "wb") as f:
            f.write(bundle_data)
        return True
    except Exception as e:
        log(f'❌ {t("log.file.save_failed", path=output_path, error=e)}')
        log(traceback.format_exc())
        return False

def compress_bundle(
    env: UnityPy.Environment,
    compression: CompressionType = "none",
    log: LogFunc = no_log,
) -> bytes:
    """
    从 UnityPy.Environment 对象生成 bundle 文件的字节数据。
    compression: 用于控制压缩方式。
                 - "lzma": 使用 LZMA 压缩。
                 - "lz4": 使用 LZ4 压缩。
                 - "original": 保留原始压缩方式。
                 - "none": 不进行压缩。
    """
    save_kwargs = {}
    if compression == "original":
        log(f'   > {t("log.compression.original")}')
        # Not passing the 'packer' argument preserves the original compression.
    elif compression == "none":
        log(f'    > {t("log.compression.none")}')
        save_kwargs['packer'] = ""  # An empty string typically means no compression.
    else:
        log(f'    > {t("log.compression.method", method=compression.upper())}')
        save_kwargs['packer'] = compression
    
    return env.file.save(**save_kwargs)

def _save_and_crc(
    env: UnityPy.Environment,
    output_path: Path,
    original_bundle_path: Path,
    save_options: SaveOptions,
    log: LogFunc = no_log,
) -> tuple[bool, str]:
    """
    一个辅助函数，用于生成压缩bundle数据，根据需要执行CRC修正，并最终保存到文件。
    封装了保存、CRC修正的逻辑。

    Returns:
        tuple(bool, str): (是否成功, 状态消息) 的元组。
    """
    try:
        # 1. 从 env 生成修改后的压缩 bundle 数据
        log(f'\n--- {t("log.section.export_modified_bundle")} ---')
        log(f'  > {t("log.compressing_bundle_data")}')
        modified_data = compress_bundle(env, save_options.compression, log)

        final_data = modified_data
        success_message = t("message.save_success")

        if save_options.perform_crc:
            log(f'  > {t("log.crc.preparing")}')
            
            with open(original_bundle_path, "rb") as f:
                original_data = f.read()

            corrected_data = CRCUtils.apply_crc_fix(
                original_data, 
                modified_data, 
                save_options.enable_padding
            )

            if not corrected_data:
                return False, t("message.crc.correction_failed_file_not_generated", name=output_path.name)
            
            final_data = corrected_data
            success_message = t("message.save_and_crc_success")
            log(f'✅ {t("log.crc.correction_success")}')

        # 2. 将最终数据写入文件
        log(f'  > {t("log.file.writing", path=output_path)}')
        with open(output_path, "wb") as f:
            f.write(final_data)
        
        return True, success_message

    except Exception as e:
        log(f'❌ {t("log.file.save_or_crc_failed", path=output_path, error=e)}')
        log(traceback.format_exc())
        return False, t("message.save_or_crc_error", error=e)

# ====== Spine 转换工具相关 ======

def convert_skel(
    input_data: bytes | Path,
    converter_path: Path,
    target_version: str,
    output_path: Path | None = None,
    log: LogFunc = no_log,
) -> tuple[bool, bytes]:
    """
    通用的 Spine .skel 文件转换器，支持升级和降级。
    
    Args:
        input_data: 输入数据，可以是 bytes 或 Path 对象
        converter_path: 转换器可执行文件的路径
        target_version: 目标版本号 (例如 "4.2.33" 或 "3.8.75")
        output_path: 可选的输出文件路径，如果提供则将结果保存到该路径
        log: 日志记录函数
        
    Returns:
        tuple[bool, bytes]: (是否成功, 转换后的数据)
    """
    # 统一将输入数据读取为字节
    original_bytes: bytes
    if isinstance(input_data, Path):
        try:
            original_bytes = input_data.read_bytes()
        except OSError as e:
            log(f'  > ❌ {t("log.file.read_in_memory_failed", path=input_data, error=e)}')
            return False, b""
    else:
        original_bytes = input_data

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            
            # 准备输入文件
            temp_input_path = temp_dir_path / "input.skel"
            temp_input_path.write_bytes(original_bytes)

            current_version = get_skel_version(temp_input_path, log)
            if not current_version:
                log(f'  > ⚠️ {t("log.spine.skel_version_detection_failed")}')
                return False, original_bytes

            # 准备输出文件
            temp_output_path = output_path if output_path else temp_dir_path / "output.skel"
            
            command = [
                str(converter_path),
                str(temp_input_path),
                str(temp_output_path),
                "-v",
                target_version
            ]
            
            log(f'    > {t("log.spine.converting_skel", name=temp_input_path.name)}')
            log(f'      > {t("log.spine.version_conversion", current=current_version, target=target_version)}')
            log(f'      > {t("log.spine.executing_command", command=" ".join(command))}')
            
            result = subprocess.run(
                command, 
                capture_output=True, 
                text=True, 
                encoding='utf-8', 
                errors='ignore',
            )
            
            if result.returncode == 0:
                return True, temp_output_path.read_bytes()
            else:
                log(f'      ✗ {t("log.spine.skel_conversion_failed")}:')
                log(f"        stdout: {result.stdout.strip()}")
                log(f"        stderr: {result.stderr.strip()}")
                return False, original_bytes

    except Exception as e:
        log(f'    ❌ {t("log.error_detail", error=e)}')
        return False, original_bytes

def _handle_skel_upgrade(
    skel_bytes: bytes,
    resource_name: str,
    spine_options: SpineOptions | None = None,
    log: LogFunc = no_log,
) -> bytes:
    """
    处理 .skel 文件的版本检查和升级。
    如果无需升级或升级失败，则返回原始字节。
    """

    log(f'    > {t("log.spine.skel_detected", name=resource_name)}')

    # 检查Spine升级功能是否可用
    if spine_options is None or not spine_options.is_enabled():
        return skel_bytes
    
    try:
        # 检测 skel 的 spine 版本
        current_version = get_skel_version(skel_bytes, log)
        target_major_minor = ".".join(spine_options.target_version.split('.')[:2])
        
        # 仅在主版本或次版本不匹配时才尝试升级
        if current_version and not current_version.startswith(target_major_minor):
            log(f'      > {t("log.spine.version_mismatch_converting", current=current_version, target=spine_options.target_version)}')

            skel_success, upgraded_content = convert_skel(
                input_data=skel_bytes,
                converter_path=spine_options.converter_path,
                target_version=spine_options.target_version,
                log=log
            )
            if skel_success:
                log(f'    > {t("log.spine.skel_conversion_success", name=resource_name)}')
                return upgraded_content
            else:
                log(f'    ❌ {t("log.spine.skel_conversion_failed_using_original", name=resource_name)}')

    except Exception as e:
        log(f'      ❌ {t("log.error_detail", error=e)}')

    # 默认返回原始字节
    return skel_bytes

def _run_spine_atlas_downgrader(
    input_atlas: Path, 
    output_dir: Path, 
    converter_path: Path,
    log: LogFunc = no_log
) -> bool:
    """使用 SpineAtlasDowngrade.exe 转换图集数据。"""
    try:
        # 转换器需要在源图集所在的目录中找到源PNG文件。
        # input_atlas 路径已指向包含所有必要文件的临时目录。
        cmd = [str(converter_path), str(input_atlas), str(output_dir)]
        log(f'    > {t("log.spine.converting_atlas", name=input_atlas.name)}')
        log(f'      > {t("log.spine.executing_command", command=" ".join(cmd))}')
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', check=False)
        
        if result.returncode == 0:
            return True
        else:
            log(f'      ✗ {t("log.spine.atlas_conversion_failed")}:')
            log(f"        stdout: {result.stdout.strip()}")
            log(f"        stderr: {result.stderr.strip()}")
            return False
    except Exception as e:
        log(f'      ✗ {t("log.error_detail", error=e)}')
        return False

def _process_spine_group_downgrade(
    skel_path: Path,
    atlas_path: Path,
    output_dir: Path,
    downgrade_options: SpineDowngradeOptions,
    log: LogFunc = no_log,
) -> None:
    """
    处理单个Spine资产组（skel, atlas, pngs）的降级。
    始终尝试进行降级操作。
    """
    version = get_skel_version(skel_path, log)
    log(f"    > {t('log.spine.version_detected_downgrading', version=version or t('common.unknown'))}")
    with tempfile.TemporaryDirectory() as conv_out_dir_str:
        conv_output_dir = Path(conv_out_dir_str)
        
        # 降级 Atlas 和关联的 PNG
        atlas_success = _run_spine_atlas_downgrader(
            atlas_path, conv_output_dir, downgrade_options.atlas_converter_path, log
        )
        
        if atlas_success:
            log(f'      > {t("log.spine.atlas_downgrade_success")}')
            for converted_file in conv_output_dir.iterdir():
                shutil.copy2(converted_file, output_dir / converted_file.name)
                log(f"        - {converted_file.name}")
        else:
            log(f'      ✗ {t("log.spine.atlas_downgrade_failed")}.')

        # 降级 Skel
        output_skel_path = output_dir / skel_path.name
        skel_success, _ = convert_skel(
            input_data=skel_path,
            converter_path=downgrade_options.skel_converter_path,
            target_version=downgrade_options.target_version,
            output_path=output_skel_path,
            log=log
        )
        if not skel_success:
            log(f'    ✗ {t("log.spine.skel_conversion_failed_using_original")}')


# ====== 寻找对应文件 ======

def get_filename_prefix(filename: str, log: LogFunc = no_log) -> tuple[str | None, str]:
    """
    从旧版Mod文件名中提取用于搜索新版文件的前缀。
    返回 (前缀字符串, 状态消息) 的元组。
    """
    # 1. 通过日期模式确定文件名位置
    date_match = re.search(r'\d{4}-\d{2}-\d{2}', filename)
    if not date_match:
        msg = t("message.search.date_pattern_not_found", filename=filename)
        log(f'  > {t("common.fail")}: {msg}')
        return None, msg

    # 2. 向前查找可能的日服额外文件名部分
    prefix_end_index = date_match.start()
    before_date = filename[:prefix_end_index].removesuffix('-')
    # 例如在 "...-textures-YYYY-MM-DD..." 中的 "textures"

    parts = before_date.split('-')
    last_part = parts[-1] if parts else ''
    
    # 检查最后一个部分是否是日服版额外的资源类型
    resource_types = {
        'textures', 'assets', 'textassets', 'materials',
        "animationclip", "audio", "meshes", "prefabs", "timelines"
    }
    
    if last_part.lower() in resource_types:
        # 如果找到了资源类型，则前缀不应该包含这个部分
        search_prefix = before_date.removesuffix(f'-{last_part}') + '-'
    else:
        search_prefix = filename[:prefix_end_index]

    return search_prefix, t("message.search.prefix_extracted")

def find_new_bundle_path(
    old_mod_path: Path,
    game_resource_dir: Path | list[Path],
    log: LogFunc = no_log,
) -> tuple[Path | None, str]:
    """
    根据旧版Mod文件，在游戏资源目录中智能查找对应的新版文件。
    支持单个目录路径或目录路径列表。
    返回 (找到的路径对象, 状态消息) 的元组。
    """
    # TODO: 只用Texture2D比较好像不太对，但是it works

    if not old_mod_path.exists():
        return None, t("message.search.check_file_exists", path=old_mod_path)

    log(t("log.search.searching_for_file", name=old_mod_path.name))

    # 1. 提取文件名前缀
    prefix, prefix_message = get_filename_prefix(str(old_mod_path.name), log)
    if not prefix:
        return None, prefix_message
    log(f"  > {t('log.search.file_prefix', prefix=prefix)}")
    extension = '.bundle'

    # 2. 处理单个目录或目录列表
    if isinstance(game_resource_dir, Path):
        search_dirs = [game_resource_dir]
    else:
        search_dirs = game_resource_dir

    # 3. 查找所有候选文件（前缀相同且扩展名一致）
    candidates: list[Path] = []
    for search_dir in search_dirs:
        if search_dir.exists() and search_dir.is_dir():
            dir_candidates = [f for f in search_dir.iterdir() if f.is_file() and f.name.startswith(prefix) and f.suffix == extension]
            candidates.extend(dir_candidates)
    
    if not candidates:
        msg = t("message.search.no_matching_files_in_dir")
        log(f'  > {t("common.fail")}: {msg}')
        return None, msg
    log(f"  > {t('log.search.found_candidates', count=len(candidates))}")

    # 4. 加载旧Mod获取贴图列表
    old_env = load_bundle(old_mod_path, log)
    if not old_env:
        msg = t("message.search.load_old_mod_failed")
        log(f'  > {t("common.fail")}: {msg}')
        return None, msg
    
    old_textures_map = {obj.read().m_Name for obj in old_env.objects if obj.type.name == "Texture2D"}
    
    if not old_textures_map:
        msg = t("message.search.no_texture2d_in_old_mod")
        log(f'  > {t("common.fail")}: {msg}')
        return None, msg
    log(f"  > {t('log.search.old_mod_texture_count', count=len(old_textures_map))}")

    # 5. 遍历候选文件，找到第一个包含匹配贴图的
    for candidate_path in candidates:
        log(f"  - {t('log.search.checking_candidate', name=candidate_path.name)}")
        
        env = load_bundle(candidate_path, log)
        if not env: continue
        
        for obj in env.objects:
            if obj.type.name == "Texture2D" and obj.read().m_Name in old_textures_map:
                msg = t("message.search.new_file_confirmed", name=candidate_path.name)
                log(f"  ✅ {msg}")
                return candidate_path, msg
    
    msg = t("message.search.no_matching_texture_found")
    log(f'  > {t("common.fail")}: {msg}')
    return None, msg


# ====== 资源处理相关 ======

def _apply_replacements(
    env: UnityPy.Environment,
    replacement_map: dict[AssetKey, AssetContent],
    key_func: KeyGeneratorFunc,
    log: LogFunc = no_log,
) -> tuple[int, list[str], set[AssetKey]]:
    """
    将“替换清单”中的资源应用到目标环境中。

    Args:
        env: 目标 UnityPy 环境。
        replacement_map: 资源替换清单，格式为 { asset_key: content }。
        key_func: 用于从目标环境中的对象生成 asset_key 的函数。
        log: 日志记录函数。

    Returns:
        一个元组 (成功替换的数量, 成功替换的资源日志列表, 未能匹配的资源键集合)。
    """
    replacement_count = 0
    replaced_assets_log = []
    
    # 创建一个副本用于操作，因为我们会从中移除已处理的项
    tasks = replacement_map.copy()

    for obj in env.objects:
        if not tasks:  # 如果清单空了，就提前退出
            break
        
        data = obj.read()
        asset_key = key_func(obj, data)

        if asset_key in tasks:
            content = tasks.pop(asset_key)
            resource_name = getattr(data, 'm_Name', t("log.unnamed_resource", type=obj.type.name))
            
            try:
                if obj.type.name == "Texture2D":
                    data.image = content
                    data.save()
                elif obj.type.name == "TextAsset":
                    # content 是 bytes，需要解码成 str
                    data.m_Script = content.decode("utf-8", "surrogateescape")
                    data.save()
                elif obj.type.name == "Mesh":
                    obj.set_raw_data(content)
                else: # 适用于 "ALL" 模式下的其他类型
                    obj.set_raw_data(content)

                replacement_count += 1
                log_message = f"  - {resource_name} ({obj.type.name})"
                replaced_assets_log.append(log_message)

            except Exception as e:
                log(f'  ❌ {t("common.error")}: {t("log.replace_resource_failed", name=resource_name, type=obj.type.name, error=e)}')

    return replacement_count, replaced_assets_log, set(tasks.keys())

def process_asset_packing(
    target_bundle_path: Path,
    asset_folder: Path,
    output_dir: Path,
    save_options: SaveOptions,
    spine_options: SpineOptions | None = None,
    log: LogFunc = no_log,
) -> tuple[bool, str]:
    """
    从指定文件夹中，将同名的资源打包到指定的 Bundle 中。
    支持 .png, .skel, .atlas 文件。
    - .png 文件将替换同名的 Texture2D 资源 (文件名不含后缀)。
    - .skel 和 .atlas 文件将替换同名的 TextAsset 资源 (文件名含后缀)。
    可选地升级 Spine 动画的 Skel 资源版本。
    此函数将生成的文件保存在工作目录中，以便后续进行"覆盖原文件"操作。
    因为打包资源的操作在原理上是替换目标Bundle内的资源，因此里面可能有混用打包和替换的叫法。
    返回 (是否成功, 状态消息) 的元组。
    
    Args:
        target_bundle_path: 目标Bundle文件的路径
        asset_folder: 包含待打包资源的文件夹路径
        output_dir: 输出目录，用于保存生成的更新后文件
        save_options: 保存和CRC修正的选项
        spine_options: Spine资源升级的选项
        log: 日志记录函数，默认为空函数
    """
    try:
        env = load_bundle(target_bundle_path, log)
        if not env:
            return False, t("message.packer.load_target_bundle_failed")
        
        # 1. 从文件夹构建"替换清单"
        replacement_map: dict[AssetKey, AssetContent] = {}
        supported_extensions = {".png", ".skel", ".atlas"}
        input_files = [f for f in asset_folder.iterdir() if f.is_file() and f.suffix.lower() in supported_extensions]

        if not input_files:
            msg = t("message.packer.no_supported_files_found", extensions=', '.join(supported_extensions))
            log(f"⚠️ {t('common.warning')}: {msg}")
            return False, msg

        for file_path in input_files:
            asset_key: AssetKey
            content: AssetContent
            if file_path.suffix.lower() == ".png":
                asset_key = file_path.stem
                content = Image.open(file_path).convert("RGBA")
            else: # .skel, .atlas
                asset_key = file_path.name
                with open(file_path, "rb") as f:
                    content = f.read()
                
                if file_path.suffix.lower() == '.skel':
                    content = _handle_skel_upgrade(
                        skel_bytes=content,
                        resource_name=asset_key,
                        spine_options=spine_options,
                        log=log
                    )
            replacement_map[asset_key] = content
        
        original_tasks_count = len(replacement_map)
        log(t("log.packer.found_files_to_process", count=original_tasks_count))

        # 2. 定义用于在 bundle 中查找资源的 key 生成函数
        def key_func(obj: UnityPy.classes.Object, data: Any) -> AssetKey | None:
            if obj.type.name in ["Texture2D", "TextAsset"]:
                return data.m_Name
            return None

        # 3. 应用替换
        replacement_count, _, unmatched_keys = _apply_replacements(env, replacement_map, key_func, log)

        if replacement_count == 0:
            log(f"⚠️ {t('common.warning')}: {t('log.packer.no_assets_packed')}")
            log(t("log.packer.check_files_and_bundle"))
            return False, t("message.packer.no_matching_assets_to_pack")
        
        log(f'\n{t("log.packer.packing_complete", success=replacement_count, total=original_tasks_count)}')

        # 报告未被打包的文件
        if unmatched_keys:
            log(f"⚠️ {t('common.warning')}: {t('log.packer.unmatched_files_warning')}:")
            # 为了找到原始文件名，我们需要反向查找
            original_filenames = {
                f.stem if f.suffix.lower() == '.png' else f.name: f.name for f in input_files
            }
            for key in sorted(unmatched_keys):
                log(f"  - {original_filenames.get(key, key)} ({t('log.packer.attempted_match', key=key)})")

        # 4. 保存和修正
        output_path = output_dir / target_bundle_path.name
        save_ok, save_message = _save_and_crc(
            env=env,
            output_path=output_path,
            original_bundle_path=target_bundle_path,
            save_options=save_options,
            log=log
        )

        if not save_ok:
            return False, save_message

        log(t("log.file.saved", path=output_path))
        log(f"\n🎉 {t('log.status.process_complete')}")
        return True, t("message.packer.process_complete", count=replacement_count, button=t("action.replace_original"))

    except Exception as e:
        log(f"\n❌ {t('common.error')}: {t('log.error_detail', error=e)}")
        log(traceback.format_exc())
        return False, t("message.error_during_process", error=e)

def process_asset_extraction(
    bundle_path: Path,
    output_dir: Path,
    asset_types_to_extract: set[str],
    downgrade_options: SpineDowngradeOptions | None = None,
    log: LogFunc = no_log,
) -> tuple[bool, str]:
    """
    从指定的 Bundle 文件中提取选定类型的资源到输出目录。
    支持 Texture2D (保存为 .png) 和 TextAsset (按原名保存)。
    如果启用了Spine降级选项，将自动处理Spine 4.x到3.8的降级。

    Args:
        bundle_path: 目标 Bundle 文件的路径。
        output_dir: 提取资源的保存目录。
        asset_types_to_extract: 需要提取的资源类型集合 (如 {"Texture2D", "TextAsset"})。
        downgrade_options: Spine资源降级的选项。
        log: 日志记录函数。

    Returns:
        一个元组 (是否成功, 状态消息)。
    """
    try:
        log("\n" + "="*50)
        log(t("log.extractor.starting_extraction", filename=bundle_path.name))
        log(t("log.extractor.extraction_types", types=', '.join(asset_types_to_extract)))
        log(f"{t('ui.label.output_dir')}: {output_dir}")

        env = load_bundle(bundle_path, log)
        if not env:
            return False, t("message.load_failed")

        output_dir.mkdir(parents=True, exist_ok=True)
        downgrade_enabled = downgrade_options and downgrade_options.is_valid()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_extraction_dir = Path(temp_dir)
            log(f"  > {t('log.extractor.using_temp_dir', path=temp_extraction_dir)}")

            # --- 阶段 1: 统一提取所有相关资源到临时目录 ---
            log(f'\n--- {t("log.section.extract_to_temp")} ---')
            extraction_count = 0
            for obj in env.objects:
                if obj.type.name not in asset_types_to_extract:
                    continue
                try:
                    data = obj.read()
                    resource_name = getattr(data, 'm_Name', None)
                    if not resource_name:
                        log(f"  > {t('log.extractor.skipping_unnamed', type=obj.type.name)}")
                        continue

                    if obj.type.name == "TextAsset":
                        dest_path = temp_extraction_dir / resource_name
                        asset_bytes = data.m_Script.encode("utf-8", "surrogateescape")
                        dest_path.write_bytes(asset_bytes)
                    elif obj.type.name == "Texture2D":
                        dest_path = temp_extraction_dir / f"{resource_name}.png"
                        data.image.convert("RGBA").save(dest_path)
                    
                    log(f"  - {dest_path.name}")
                    extraction_count += 1
                except Exception as e:
                    log(f"  ❌ {t('log.extractor.extraction_failed', name=getattr(data, 'm_Name', 'N/A'), error=e)}")

            if extraction_count == 0:
                msg = t("message.extractor.no_assets_found")
                log(f"⚠️ {msg}")
                return True, msg

            # --- 阶段 2: 处理并移动文件 ---
            if not downgrade_enabled:
                log(f'\n--- {t("log.section.move_to_output")} ---')
                for item in temp_extraction_dir.iterdir():
                    shutil.copy2(item, output_dir / item.name)
            else:
                log(f'\n--- {t("log.section.process_spine_downgrade")} ---')
                processed_files = set()
                skel_files = list(temp_extraction_dir.glob("*.skel"))

                if not skel_files:
                    log(f'  > {t("log.spine.no_skel_found")}')
                
                for skel_path in skel_files:
                    base_name = skel_path.stem
                    atlas_path = skel_path.with_suffix(".atlas")
                    log(f"\n  > {t('log.extractor.processing_asset_group', name=base_name)}")

                    if not atlas_path.exists():
                        log(f"    - {t('common.warning')}: {t('log.spine.missing_matching_atlas', skel=skel_path.name, atlas=atlas_path.name)}")
                        continue
                    
                    # 标记此资产组中的所有文件为已处理
                    png_paths = list(temp_extraction_dir.glob(f"{base_name}*.png"))
                    processed_files.add(skel_path)
                    processed_files.add(atlas_path)
                    processed_files.update(png_paths)

                    # 调用辅助函数处理该资产组
                    _process_spine_group_downgrade(
                        skel_path, atlas_path, output_dir, downgrade_options, log
                    )
                
                # --- 阶段 3: 复制剩余的独立文件 ---
                remaining_files = [item for item in temp_extraction_dir.iterdir() if item not in processed_files]
                
                if remaining_files:
                    log(f'\n--- {t("log.section.copy_standalone_files")} ---')
                    for item in remaining_files:
                        log(f"  - {t('log.extractor.copying_file', name=item.name)}")
                        shutil.copy2(item, output_dir / item.name)

        total_files_extracted = len(list(output_dir.iterdir()))
        success_msg = t("message.extractor.extraction_complete", count=total_files_extracted)
        log(f"\n🎉 {success_msg}")
        return True, success_msg

    except Exception as e:
        log(f"\n❌ {t('common.error')}: {t('log.error_detail', error=e)}")
        log(traceback.format_exc())
        return False, t("message.error_during_process", error=e)

def _extract_assets_from_bundle(
    env: UnityPy.Environment,
    asset_types_to_replace: set[str],
    key_func: KeyGeneratorFunc,
    spine_options: SpineOptions | None,
    log: LogFunc = no_log,
) -> dict[AssetKey, AssetContent]:
    """
    从源 bundle 的 env 构建替换清单
    即其他函数中使用的replacement_map
    """
    replacement_map: dict[AssetKey, AssetContent] = {}
    replace_all = "ALL" in asset_types_to_replace

    for obj in env.objects:
        if replace_all or (obj.type.name in asset_types_to_replace):
            data = obj.read()
            asset_key = key_func(obj, data)
            content = None
            resource_name = getattr(data, 'm_Name', t("log.unnamed_resource", type=obj.type.name))

            if obj.type.name == "Texture2D":
                content = data.image
            elif obj.type.name == "TextAsset":
                asset_bytes = data.m_Script.encode("utf-8", "surrogateescape")
                if resource_name.lower().endswith('.skel'):
                    content = _handle_skel_upgrade(
                        skel_bytes=asset_bytes,
                        resource_name=resource_name,
                        spine_options=spine_options,
                        log=log
                    )
                else:
                    content = asset_bytes
            elif obj.type.name == "Mesh":
                content = obj.get_raw_data()
            elif replace_all:
                content = obj.get_raw_data()

            if content is not None:
                replacement_map[asset_key] = content
    
    return replacement_map

def _b2b_replace(
    old_bundle_path: Path,
    new_bundle_path: Path,
    asset_types_to_replace: set[str],
    spine_options: SpineOptions | None = None,
    log: LogFunc = no_log,
) -> tuple[UnityPy.Environment | None, int]:
    """
    执行 Bundle-to-Bundle 的核心替换逻辑。
    asset_types_to_replace: 要替换的资源类型集合（如 {"Texture2D", "TextAsset", "Mesh"} 的子集 或 {"ALL"}）
    按顺序尝试多种匹配策略（path_id, name_type），一旦有策略成功替换了至少一个资源，就停止并返回结果。
    返回一个元组 (modified_env, replacement_count)，如果失败则 modified_env 为 None。
    """
    # 1. 加载 bundles
    log(t("log.b2b.extracting_from_old_bundle", types=', '.join(asset_types_to_replace)))
    old_env = load_bundle(old_bundle_path, log)
    if not old_env:
        return None, 0
    
    log(t("log.b2b.loading_new_bundle"))
    new_env = load_bundle(new_bundle_path, log)
    if not new_env:
        return None, 0

    # 定义匹配策略
    strategies: list[tuple[str, KeyGeneratorFunc]] = [
        ('path_id', lambda obj, data: obj.path_id),
        ('name_type', lambda obj, data: (data.m_Name, obj.type.name))
    ]

    for name, key_func in strategies:
        log(f'\n{t("log.b2b.trying_strategy", name=name)}')
        
        # 2. 根据当前策略从旧版 bundle 构建“替换清单”
        log(f'  > {t("log.b2b.extracting_from_old_bundle_simple")}')
        old_assets_map = _extract_assets_from_bundle(
            old_env, asset_types_to_replace, key_func, spine_options, log
        )
        
        if not old_assets_map:
            log(f"  > ⚠️ {t('common.warning')}: {t('log.b2b.strategy_no_assets_found', name=name)}")
            continue

        log(f'  > {t("log.b2b.extraction_complete", name=name, count=len(old_assets_map))}')

        # 3. 根据当前策略应用替换
        log(f'  > {t("log.b2b.writing_to_new_bundle")}')
        
        replacement_count, replaced_logs, _ \
        = _apply_replacements(new_env, old_assets_map, key_func, log)
        
        # 4. 如果当前策略成功替换了至少一个资源，就结束
        if replacement_count > 0:
            log(f"\n✅ {t('log.b2b.strategy_success', name=name, count=replacement_count)}:")
            for item in replaced_logs:
                log(item)
            return new_env, replacement_count

        log(f'  > {t("log.b2b.strategy_no_match", name=name)}')

    # 5. 所有策略都失败了
    log(f"\n⚠️ {t('common.warning')}: {t('log.b2b.all_strategies_failed', types=', '.join(asset_types_to_replace))}")
    return None, 0

def process_mod_update(
    old_mod_path: Path,
    new_bundle_path: Path,
    output_dir: Path,
    asset_types_to_replace: set[str],
    save_options: SaveOptions,
    spine_options: SpineOptions | None = None,
    log: LogFunc = no_log,
) -> tuple[bool, str]:
    """
    自动化Mod更新流程。
    
    该函数是Mod更新工具的核心处理函数，负责将旧版Mod中的资源替换到新版游戏资源中，
    并可选地进行CRC校验修正以确保文件兼容性。
    
    处理流程的主要阶段：
    - Bundle-to-Bundle替换：将旧版Mod中的指定类型资源替换到新版资源文件中
        - 支持替换Texture2D、TextAsset、Mesh等资源类型
        - 可选地升级Spine动画资源的Skel版本
    - CRC修正：根据选项决定是否对新生成的文件进行CRC校验修正
    
    Args:
        old_mod_path: 旧版Mod文件的路径
        new_bundle_path: 新版游戏资源文件的路径
        output_dir: 输出目录，用于保存生成的更新后文件
        asset_types_to_replace: 需要替换的资源类型集合（如 {"Texture2D", "TextAsset"}）
        save_options: 保存和CRC修正的选项
        spine_options: Spine资源升级的选项
        log: 日志记录函数，默认为空函数
    
    Returns:
        tuple[bool, str]: (是否成功, 状态消息) 的元组
    """
    try:
        log("="*50)
        log(f'  > {t("log.mod_update.using_old_mod", name=old_mod_path.name)}')
        log(f'  > {t("log.mod_update.using_new_resource", name=new_bundle_path.name)}')

        # 进行Bundle to Bundle 替换
        log(f'\n--- {t("log.section.b2b_replace")} ---')
        modified_env, replacement_count = _b2b_replace(
            old_bundle_path=old_mod_path, 
            new_bundle_path=new_bundle_path, 
            asset_types_to_replace=asset_types_to_replace, 
            spine_options=spine_options,
            log = log
        )

        if not modified_env:
            return False, t("message.mod_update.b2b_failed")
        if replacement_count == 0:
            return False, t("message.mod_update.no_matching_assets_to_replace")
        
        log(f'  > {t("log.mod_update.b2b_complete", count=replacement_count)}')
        
        # 保存和修正文件
        output_path = output_dir / new_bundle_path.name
        save_ok, save_message = _save_and_crc(
            env=modified_env,
            output_path=output_path,
            original_bundle_path=new_bundle_path,
            save_options=save_options,
            log=log
        )

        if not save_ok:
            return False, save_message

        log(t("log.file.saved", path=output_path))
        log(f"\n🎉 {t('log.mod_update.all_processes_complete')}")
        return True, t("message.mod_update.success")

    except Exception as e:
        log(f"\n❌ {t('common.error')}: {t('log.error_processing', error=e)}")
        log(traceback.format_exc())
        return False, t("message.error_during_process", error=e)

def process_batch_mod_update(
    mod_file_list: list[Path],
    search_paths: list[Path],
    output_dir: Path,
    asset_types_to_replace: set[str],
    save_options: SaveOptions,
    spine_options: SpineOptions | None,
    log: LogFunc = no_log,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> tuple[int, int, list[str]]:
    """
    执行批量Mod更新的核心逻辑。

    Args:
        mod_file_list: 待更新的旧Mod文件路径列表。
        search_paths: 用于查找新版bundle文件的目录列表。
        output_dir: 输出目录。
        asset_types_to_replace: 需要替换的资源类型集合。
        save_options: 保存和CRC修正的选项。
        spine_options: Spine资源升级的选项。
        log: 日志记录函数。
        progress_callback: 进度回调函数，用于更新UI。
                           接收 (当前索引, 总数, 文件名)。

    Returns:
        tuple[int, int, list[str]]: (成功计数, 失败计数, 失败任务详情列表)
    """
    total_files = len(mod_file_list)
    success_count = 0
    fail_count = 0
    failed_tasks = []

    # 遍历每个旧Mod文件
    for i, old_mod_path in enumerate(mod_file_list):
        current_progress = i + 1
        filename = old_mod_path.name
        
        if progress_callback:
            progress_callback(current_progress, total_files, filename)

        log("\n" + "=" * 50)
        log(t("log.status.processing_batch", current=current_progress, total=total_files, filename=filename))

        # 查找对应的新资源文件
        new_bundle_path, find_message = find_new_bundle_path(
            old_mod_path, search_paths, log
        )

        if not new_bundle_path:
            log(f'❌ {t("log.search.find_failed", message=find_message)}')
            fail_count += 1
            failed_tasks.append(f"{filename} - {t('log.search.find_failed', message=find_message)}")
            continue

        # 执行Mod更新处理
        success, process_message = process_mod_update(
            old_mod_path=old_mod_path,
            new_bundle_path=new_bundle_path,
            output_dir=output_dir,
            asset_types_to_replace=asset_types_to_replace,
            save_options=save_options,
            spine_options=spine_options,
            log=log
        )

        if success:
            log(f'✅ {t("log.mod_update.process_success", filename=filename)}')
            success_count += 1
        else:
            log(f'❌ {t("log.mod_update.process_failed", filename=filename, message=process_message)}')
            fail_count += 1
            failed_tasks.append(f"{filename} - {process_message}")

    return success_count, fail_count, failed_tasks

# ====== 日服处理相关 ======

def find_jp_bundle_by_type(
    source_jp_path: Path,
    target_type: Literal['textassets', 'textures'],
    search_dirs: Path | list[Path],
    log: LogFunc = no_log,
) -> Path | None:
    """
    根据一个日服bundle文件，查找指定类型的对应文件。
    例如，根据 textassets 文件查找对应的 textures 文件。

    Args:
        source_jp_path: 已知的日服bundle文件路径。
        target_type: 要查找的文件类型 ('textassets' 或 'textures')。
        search_dirs: 用于查找的目录列表。
        log: 日志记录函数。

    Returns:
        找到的对应文件的路径，如果未找到则返回 None。
    """
    if isinstance(search_dirs, Path):
        search_dirs = [search_dirs]

    # 使用 get_filename_prefix 获取通用的文件名前缀
    prefix, prefix_message = get_filename_prefix(source_jp_path.name, log)
    if not prefix:
        log(f'  > ❌ {t("log.search.find_failed")}: {prefix_message}')
        return None
    log(f"  > {t('log.search.using_prefix', prefix=prefix)}")
    target_keyword = f'-{target_type}-'

    if target_keyword in source_jp_path.name:
        log(f"  > {t('log.jp_convert.source_is_target_type', type=target_type)}")
        return source_jp_path

    # 在所有搜索目录中查找匹配的文件
    for search_dir in search_dirs:
        if not (search_dir.exists() and search_dir.is_dir()):
            continue
        
        for file_path in search_dir.iterdir():
            # 检查文件是否以通用前缀开头，并包含目标类型的关键词
            if file_path.is_file() and file_path.name.startswith(prefix) and target_keyword in file_path.name:
                log(f"  ✅ {t('log.jp_convert.found_match', path=file_path)}")
                return file_path
    
    log(f'  > ❌ {t("log.jp_convert.no_match_found")}')
    return None

def find_jp_counterparts(
    global_bundle_path: Path,
    search_dirs: list[Path],
    log: LogFunc = no_log,
) -> tuple[Path | None, Path | None]:
    """
    根据国际服bundle文件，查找其对应的日服 TextAsset 和 Texture2D bundle 文件。

    Args:
        global_bundle_path: 国际服bundle文件的路径。
        search_dirs: 用于查找的目录列表。
        log: 日志记录函数。

    Returns:
        一个元组 (jp_text_path, jp_tex2d_path)，未找到则为 None。
    """
    log(t("log.jp_convert.searching_jp_counterparts", name=global_bundle_path.name))

    # 1. 从国际服文件名提取前缀
    prefix, prefix_message = get_filename_prefix(global_bundle_path.name, log)
    if not prefix:
        log(f'  > ❌ {t("log.search.find_failed")}: {prefix_message}')
        return None, None
    log(f"  > {t('log.search.using_prefix', prefix=prefix)}")

    jp_text_path: Path | None = None
    jp_tex2d_path: Path | None = None

    # 2. 在搜索目录中查找匹配前缀且包含特定关键词的文件
    for search_dir in search_dirs:
        if not (search_dir.exists() and search_dir.is_dir()):
            continue
        
        for file_path in search_dir.iterdir():
            if file_path.is_file() and file_path.name.startswith(prefix):
                if '-textassets-' in file_path.name:
                    jp_text_path = file_path
                    log(f"  > {t('log.jp_convert.found_jp_asset', type='TextAsset', name=file_path.name)}")
                elif '-textures-' in file_path.name:
                    jp_tex2d_path = file_path
                    log(f"  > {t('log.jp_convert.found_jp_asset', type='Texture2D', name=file_path.name)}")
            
            # 如果两个都找到了，可以提前结束搜索
            if jp_text_path and jp_tex2d_path:
                return jp_text_path, jp_tex2d_path

    return jp_text_path, jp_tex2d_path

def process_jp_to_global_conversion(
    global_bundle_path: Path,
    jp_textasset_bundle_path: Path,
    jp_texture2d_bundle_path: Path,
    output_dir: Path,
    save_options: SaveOptions,
    log: LogFunc = no_log,
) -> tuple[bool, str]:
    """
    处理日服转国际服的转换。
    
    将日服的两个资源bundle（textasset、texture2d）合并到国际服的基础bundle文件中。
    
    Args:
        global_bundle_path: 国际服bundle文件路径（作为基础）
        jp_textasset_bundle_path: 日服textasset bundle文件路径
        jp_texture2d_bundle_path: 日服texture2d bundle文件路径
        output_dir: 输出目录
        save_options: 保存和CRC修正的选项
        log: 日志记录函数
    
    Returns:
        tuple[bool, str]: (是否成功, 状态消息) 的元组
    """
    try:
        log("="*50)
        log(t("log.jp_convert.starting_jp_to_global"))
        log(f'  > {t("log.jp_convert.global_base_file", name=global_bundle_path.name)}')
        log(f'  > {t("log.jp_convert.jp_asset_file", type="TextAsset", name=jp_textasset_bundle_path.name)}')
        log(f'  > {t("log.jp_convert.jp_asset_file", type="Texture2D", name=jp_texture2d_bundle_path.name)}')
        
        # 加载所有 bundles
        global_env = load_bundle(global_bundle_path, log)
        if not global_env:
            return False, t("message.jp_convert.load_global_failed")
        
        jp_textasset_env = load_bundle(jp_textasset_bundle_path, log)
        if not jp_textasset_env:
            return False, t("message.jp_convert.load_jp_asset_failed", type="TextAsset")
        
        jp_texture2d_env = load_bundle(jp_texture2d_bundle_path, log)
        if not jp_texture2d_env:
            return False, t("message.jp_convert.load_jp_asset_failed", type="Texture2D")
        
        log(f'\n--- {t("log.section.merging_assets")} ---')

        # 1. 从日服 bundles 构建源资源映射，以便快速查找
        #    键是资源名，值是 UnityPy 的 Object 对象
        source_assets = {}
        for obj in jp_textasset_env.objects:
            if obj.type.name == "TextAsset":
                source_assets[obj.read().m_Name] = obj
        for obj in jp_texture2d_env.objects:
            if obj.type.name == "Texture2D":
                source_assets[obj.read().m_Name] = obj
        
        # 2. 准备替换和添加
        #    `replaced_or_added` 用于跟踪已处理的源资源
        replaced_or_added = set()
        textasset_count = 0
        texture2d_count = 0

        # --- 阶段一: 替换现有资源 ---
        # 遍历目标环境，用源资源的数据更新匹配的现有资源
        for obj in global_env.objects:
            if obj.type.name not in ["TextAsset", "Texture2D"]:
                continue
            
            data = obj.read()
            resource_name = data.m_Name
            
            if resource_name in source_assets:
                source_obj = source_assets[resource_name]
                
                # 确保类型匹配
                if obj.type.name != source_obj.type.name:
                    log(f"  > ⚠️ {t('log.jp_convert.type_mismatch', name=resource_name, target=obj.type.name, source=source_obj.type.name)}")
                    continue

                log(f"  > {t('log.jp_convert.replacing_asset', type=obj.type.name, name=resource_name)}")
                source_data = source_obj.read()
                
                if obj.type.name == "TextAsset":
                    data.m_Script = source_data.m_Script
                    textasset_count += 1
                elif obj.type.name == "Texture2D":
                    data.image = source_data.image
                    texture2d_count += 1
                
                data.save() # 将修改保存回对象
                replaced_or_added.add(resource_name)

        # --- 阶段二: 添加新资源 ---
        # 遍历源资源映射，将未被用于替换的资源添加到目标环境
        for resource_name, source_obj in source_assets.items():
            if resource_name not in replaced_or_added:
                log(f"  > {t('log.jp_convert.adding_asset', type=source_obj.type.name, name=resource_name)}")
                
                # 关键步骤: 将源对象的 assets_file 指向目标环境的 file 对象
                # 这使得该对象成为目标环境的一部分
                source_obj.assets_file = global_env.file
                global_env.objects.append(source_obj)
                
                if source_obj.type.name == "TextAsset":
                    textasset_count += 1
                elif source_obj.type.name == "Texture2D":
                    texture2d_count += 1

        log(f"\n  > {t('log.jp_convert.merge_complete', text_count=textasset_count, tex_count=texture2d_count)}")
        
        # 3. 保存最终文件
        output_path = output_dir / global_bundle_path.name
        save_ok, save_message = _save_and_crc(
            env=global_env,
            output_path=output_path,
            original_bundle_path=global_bundle_path,
            save_options=save_options,
            log=log
        )
        
        if not save_ok:
            return False, save_message
        
        log(t("log.file.saved", path=output_path))
        log(f"\n🎉 {t('log.jp_convert.jp_to_global_complete')}")
        return True, t("message.jp_convert.jp_to_global_success")
        
    except Exception as e:
        log(f"\n❌ {t('common.error')}: {t('log.jp_convert.error_jp_to_global', error=e)}")
        log(traceback.format_exc())
        return False, t("message.jp_convert.conversion_error", error=e)

def process_global_to_jp_conversion(
    global_bundle_path: Path,
    jp_textasset_bundle_path: Path,
    jp_texture2d_bundle_path: Path,
    output_dir: Path,
    save_options: SaveOptions,
    log: LogFunc = no_log,
) -> tuple[bool, str]:
    """
    处理国际服转日服的转换。
    
    将一个国际服格式的bundle文件，使用日服bundle作为模板，
    拆分为日服格式的两个bundle文件（textasset 和 texture2d）。
    
    Args:
        global_bundle_path: 待转换的国际服bundle文件路径。
        jp_textasset_bundle_path: 日服textasset bundle文件路径（用作模板）。
        jp_texture2d_bundle_path: 日服texture2d bundle文件路径（用作模板）。
        output_dir: 输出目录。
        save_options: 保存选项（函数内部会自动禁用CRC修正）。
        log: 日志记录函数。
    
    Returns:
        tuple[bool, str]: (是否成功, 状态消息) 的元组
    """
    try:
        log("="*50)
        log(t("log.jp_convert.starting_global_to_jp"))
        log(f'  > {t("log.jp_convert.global_source_file", name=global_bundle_path.name)}')
        log(f'  > {t("log.jp_convert.asset_template", type="TextAsset", name=jp_textasset_bundle_path.name)}')
        log(f'  > {t("log.jp_convert.asset_template", type="Texture2D", name=jp_texture2d_bundle_path.name)}')
        
        # 1. 加载所有相关文件
        global_env = load_bundle(global_bundle_path, log)
        if not global_env:
            return False, t("message.jp_convert.load_global_source_failed")

        textasset_env = load_bundle(jp_textasset_bundle_path, log)
        if not textasset_env:
            return False, t("message.jp_convert.load_jp_template_failed", type="TextAsset")
        
        texture2d_env = load_bundle(jp_texture2d_bundle_path, log)
        if not texture2d_env:
            return False, t("message.jp_convert.load_jp_template_failed", type="Texture2D")
        
        # 2. 从国际服 bundle 构建源资源映射
        log(f'\n--- {t("log.section.extracting_from_global")} ---')
        source_assets = {}
        for obj in global_env.objects:
            if obj.type.name in ["TextAsset", "Texture2D"]:
                source_assets[obj.read().m_Name] = obj
        
        if not source_assets:
            msg = t("message.jp_convert.no_assets_in_source")
            log(f"  > ⚠️ {msg}")
            return False, msg
        log(f"  > {t('log.jp_convert.extracted_count', count=len(source_assets))}")

        # 3. 处理 TextAsset bundle
        log(f'\n--- {t("log.section.processing_asset_bundle", type="TextAsset")} ---')
        replaced_or_added_text = set()
        textasset_count = 0
        # 替换现有
        for obj in textasset_env.objects:
            if obj.type.name == "TextAsset":
                data = obj.read()
                if data.m_Name in source_assets:
                    source_obj = source_assets[data.m_Name]
                    if source_obj.type.name == "TextAsset":
                        log(f"  > {t('log.jp_convert.replacing_asset', type='TextAsset', name=data.m_Name)}")
                        data.m_Script = source_obj.read().m_Script
                        data.save()
                        replaced_or_added_text.add(data.m_Name)
                        textasset_count += 1
        # 添加新增
        for name, source_obj in source_assets.items():
            if source_obj.type.name == "TextAsset" and name not in replaced_or_added_text:
                log(f"  > {t('log.jp_convert.adding_asset', type='TextAsset', name=name)}")
                source_obj.assets_file = textasset_env.file
                textasset_env.objects.append(source_obj)
                textasset_count += 1

        # 4. 处理 Texture2D bundle
        log(f'\n--- {t("log.section.processing_asset_bundle", type="Texture2D")} ---')
        replaced_or_added_tex = set()
        texture2d_count = 0
        # 替换现有
        for obj in texture2d_env.objects:
            if obj.type.name == "Texture2D":
                data = obj.read()
                if data.m_Name in source_assets:
                    source_obj = source_assets[data.m_Name]
                    if source_obj.type.name == "Texture2D":
                        log(f"  > {t('log.jp_convert.replacing_asset', type='Texture2D', name=data.m_Name)}")
                        data.image = source_obj.read().image
                        data.save()
                        replaced_or_added_tex.add(data.m_Name)
                        texture2d_count += 1
        # 添加新增
        for name, source_obj in source_assets.items():
            if source_obj.type.name == "Texture2D" and name not in replaced_or_added_tex:
                log(f"  > {t('log.jp_convert.adding_asset', type='Texture2D', name=name)}")
                source_obj.assets_file = texture2d_env.file
                texture2d_env.objects.append(source_obj)
                texture2d_count += 1

        log(f"\n--- {t('log.section.migration_complete', text_count=textasset_count, tex_count=texture2d_count)} ---")

        # 5. 定义输出路径和保存选项
        output_textasset_path = output_dir / jp_textasset_bundle_path.name
        output_texture2d_path = output_dir / jp_texture2d_bundle_path.name
        
        # 6. 保存拆分后的 bundle 文件
        if textasset_count > 0:
            log(f'\n--- {t("log.section.saving_asset_bundle", type="TextAsset")} ---')
            save_ok, save_message = _save_and_crc(
                env=textasset_env,
                output_path=output_textasset_path,
                original_bundle_path=jp_textasset_bundle_path, # 用模板作为原始路径
                save_options=save_options,
                log=log
            )
            if not save_ok:
                return False, t("message.jp_convert.save_asset_bundle_failed", type="TextAsset", message=save_message)
        else:
            log(f'\n--- {t("log.section.no_asset_skipping_save", type="TextAsset")} ---')


        if texture2d_count > 0:
            log(f'\n--- {t("log.section.saving_asset_bundle", type="Texture2D")} ---')
            save_ok, save_message = _save_and_crc(
                env=texture2d_env,
                output_path=output_texture2d_path,
                original_bundle_path=jp_texture2d_bundle_path, # 用模板作为原始路径
                save_options=save_options,
                log=log
            )
            if not save_ok:
                return False, t("message.jp_convert.save_asset_bundle_failed", type="Texture2D", message=save_message)
        else:
            log(f'\n--- {t("log.section.no_asset_skipping_save", type="Texture2D")} ---')

        log(f'\n--- {t("log.section.conversion_complete")} ---')
        if textasset_count > 0:
            log(t("log.jp_convert.asset_bundle_saved_to", type="TextAsset", path=output_textasset_path))
        if texture2d_count > 0:
            log(t("log.jp_convert.asset_bundle_saved_to", type="Texture2D", path=output_texture2d_path))
        log(f"\n🎉 {t('log.jp_convert.global_to_jp_complete')}")
        
        return True, t("message.jp_convert.global_to_jp_success")
        
    except Exception as e:
        log(f"\n❌ {t('common.error')}: {t('log.jp_convert.error_global_to_jp', error=e)}")
        log(traceback.format_exc())
        return False, t("message.jp_convert.conversion_error", error=e)