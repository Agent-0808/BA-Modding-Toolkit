# spine.py

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from SpineAtlas import Atlas, ReadAtlasFile

from .i18n import t
from .utils import CREATE_NO_WINDOW, LogFunc, no_log


def get_skel_version(source: Path | bytes, log: LogFunc = no_log) -> str | None:
    """
    通过扫描文件或字节数据头部来查找Spine版本号。

    Args:
        source: .skel 文件的 Path 对象或其字节数据 (bytes)。
        log: 日志记录函数

    Returns:
        一个字符串,表示Spine的版本号,例如 "4.2.33"。
        如果未找到,则返回 None。
    """
    try:
        data = b''
        if isinstance(source, Path):
            if not source.exists():
                log(t("log.file.not_exist", path=source))
                return None
            with open(str(source), 'rb') as f:
                data = f.read(256)
        else:
            data = source

        header_chunk = data[:256]
        header_text = header_chunk.decode('utf-8', errors='ignore')

        match = re.search(r'(\d\.\d+\.\d+)', header_text)

        if not match:
            return None

        version_string = match.group(1)
        return version_string

    except Exception as e:
        log(t("log.error_processing", error=e))
        return None


class SkelConverter:
    """Spine .skel 文件版本转换工具类,支持升级和降级。"""

    @staticmethod
    def run(
        input_data: bytes | Path,
        converter_path: Path,
        target_version: str,
        output_path: Path | None = None,
        log: LogFunc = no_log,
    ) -> tuple[bool, bytes]:
        """
        通用的 Spine .skel 文件转换器,支持升级和降级。

        Args:
            input_data: 输入数据,可以是 bytes 或 Path 对象
            converter_path: 转换器可执行文件的路径
            target_version: 目标版本号 (例如 "4.2.33" 或 "3.8.75")
            output_path: 可选的输出文件路径,如果提供则将结果保存到该路径
            log: 日志记录函数

        Returns:
            tuple[bool, bytes]: (是否成功, 转换后的数据)
        """
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

                temp_input_path = temp_dir_path / "input.skel"
                temp_input_path.write_bytes(original_bytes)

                current_version = get_skel_version(temp_input_path, log)
                if not current_version:
                    log(f'  > ⚠️ {t("log.spine.skel_version_detection_failed")}')
                    return False, original_bytes

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
                    creationflags=CREATE_NO_WINDOW,
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

    @staticmethod
    def upgrade(
        skel_bytes: bytes,
        resource_name: str,
        enabled: bool = False,
        converter_path: Path | None = None,
        target_version: str | None = None,
        log: LogFunc = no_log,
    ) -> bytes:
        """
        处理 .skel 文件的版本检查和升级。
        如果无需升级或升级失败,则返回原始字节。
        """
        if not enabled or not converter_path or not target_version:
            return skel_bytes

        if not converter_path.exists():
            return skel_bytes

        if target_version.count(".") != 2:
            return skel_bytes

        try:
            log(f'  > {t("log.spine.skel_detected", name=resource_name)}')
            current_version = get_skel_version(skel_bytes, log)
            target_major_minor = ".".join(target_version.split('.')[:2])

            if current_version and not current_version.startswith(target_major_minor):
                log(f'    > {t("log.spine.version_mismatch_converting", current=current_version, target=target_version)}')

                skel_success, upgraded_content = SkelConverter.run(
                    input_data=skel_bytes,
                    converter_path=converter_path,
                    target_version=target_version,
                    log=log
                )
                if skel_success:
                    log(f'  > {t("log.spine.skel_conversion_success")}')
                    return upgraded_content
                else:
                    log(f'  ❌ {t("log.spine.skel_conversion_failed")}')

        except Exception as e:
            log(f'    ❌ {t("log.error_detail", error=e)}')

        return skel_bytes

    @staticmethod
    def downgrade(
        skel_path: Path,
        output_dir: Path,
        converter_path: Path,
        target_version: str,
        log: LogFunc = no_log,
    ) -> bool:
        """处理单个 .skel 文件的降级。"""
        version = get_skel_version(skel_path, log)
        log(f"    > {t('log.spine.version_detected_downgrading', version=version or t('common.unknown'))}")

        output_skel_path = output_dir / skel_path.name
        skel_success, _ = SkelConverter.run(
            input_data=skel_path,
            converter_path=converter_path,
            target_version=target_version,
            output_path=output_skel_path,
            log=log
        )
        if skel_success:
            log(f'    > {t("log.spine.skel_conversion_success", name=skel_path.name)}')
        else:
            log(f'    ✗ {t("log.spine.skel_conversion_failed")}')
        return skel_success


class SpineViewer:
    """SpineViewerCLI 工具集成类,用于查询信息和渲染预览。"""

    @staticmethod
    def query(
        skel_path: Path,
        viewer_path: Path,
        atlas_path: Path | None = None,
        log: LogFunc = no_log,
    ) -> tuple[bool, dict]:
        """
        查询 Spine skel 文件中的动画和皮肤信息。

        Args:
            skel_path: skel 文件路径
            viewer_path: SpineViewerCLI 可执行文件路径
            atlas_path: atlas 文件路径(可选)
            log: 日志记录函数

        Returns:
            tuple[bool, dict]: (是否成功, 包含 animations 和 skins 的字典)
        """
        if not skel_path.exists():
            log(f'  ❌ {t("log.file.not_exist", path=skel_path)}')
            return False, {}

        if not viewer_path.exists():
            log(f'  ❌ {t("log.file.not_exist", path=viewer_path)}')
            return False, {}

        try:
            command = [
                str(viewer_path),
                "query",
                "--all",
                str(skel_path)
            ]

            if atlas_path and atlas_path.exists():
                command.extend(["--atlas", str(atlas_path)])

            log(f'  > {t("log.spine.querying_info", name=skel_path.name)}')

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                creationflags=CREATE_NO_WINDOW,
            )

            if result.returncode != 0:
                log(f'  ✗ {t("log.spine.query_failed")}: {result.stderr.strip()}')
                return False, {}

            # 解析输出
            info = {
                'animations': [],
                'skins': []
            }

            lines = result.stdout.strip().split('\n')
            current_section = None

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # 检测区块开始标记
                if '>>>>>>>>>>>>>>> Animations >>>>>>>>>>>>>>>' in line:
                    current_section = 'animations'
                    continue
                elif '>>>>>>>>>>>>>>> Skins >>>>>>>>>>>>>>>' in line:
                    current_section = 'skins'
                    continue
                # 检测区块结束标记
                elif '<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<' in line:
                    current_section = None
                    continue
                # 跳过表头
                elif current_section and ('Name' in line or 'Duration' in line):
                    continue
                # 解析数据行
                elif current_section:
                    # Animations 格式: "Name    Duration"
                    # Skins 格式: "Name"
                    parts = line.split()
                    if parts:
                        # 提取名称(第一列)
                        name = parts[0]
                        if name and name not in ['Name', 'Duration']:
                            info[current_section].append(name)

            log(f'  > {t("log.spine.query_success", anim_count=len(info["animations"]), skin_count=len(info["skins"]))}')
            return True, info

        except Exception as e:
            log(f'  ❌ {t("log.error_detail", error=e)}')
            return False, {}

    @staticmethod
    def render(
        skel_path: Path,
        output_path: Path,
        viewer_path: Path,
        atlas_path: Path | None = None,
        animation: str = "Idle_01",
        skin: str = "",
        scale: float = 1.0,
        background: str = "#00000000",
        fmt: str = "png",
        log: LogFunc = no_log,
    ) -> tuple[bool, str]:
        """
        渲染 Spine 预览图。

        Args:
            skel_path: skel 文件路径
            output_path: 输出图片路径
            viewer_path: SpineViewerCLI 可执行文件路径
            animation: 动画名称
            skin: 皮肤名称（空字符串表示默认皮肤）
            atlas_path: atlas 文件路径（可选）
            scale: 缩放比例
            background: 背景颜色（默认透明）
            fmt: 输出格式
            log: 日志记录函数

        Returns:
            tuple[bool, str]: (是否成功, 状态消息)
        """
        if not skel_path.exists():
            msg = t("log.file.not_exist", path=skel_path)
            log(f'  ❌ {msg}')
            return False, msg

        if not viewer_path.exists():
            msg = t("log.file.not_exist", path=viewer_path)
            log(f'  ❌ {msg}')
            return False, msg

        try:
            command = [
                str(viewer_path),
                "export",
                str(skel_path),
                "-f", fmt,
                "-o", str(output_path),
                "-a", animation,
                "--scale", str(scale),
                "--color", background,
                "--margin", "0",
                "--max-resolution", "8888",
                "--time", "0",
                "--quality", "100",
                "--no-progress"
            ]

            if skin:
                command.extend(["--skins", skin])

            if atlas_path and atlas_path.exists():
                command.extend(["--atlas", str(atlas_path)])

            log(f'  > {t("log.spine.rendering_preview", name=skel_path.name, anim=animation)}')

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                creationflags=CREATE_NO_WINDOW,
            )

            if result.returncode != 0:
                msg = t("log.spine.render_failed", error=result.stderr.strip())
                log(f'  ✗ {msg}')
                return False, msg

            if output_path.exists():
                msg = t("log.spine.render_success", path=output_path)
                log(f'  ✓ {msg}')
                return True, msg
            else:
                msg = t("log.spine.render_file_not_found")
                log(f'  ✗ {msg}')
                return False, msg

        except Exception as e:
            msg = t("log.error_detail", error=e)
            log(f'  ❌ {msg}')
            return False, msg


def atlas_downgrade(
    atlas_path: Path,
    output_dir: Path,
    log: LogFunc = no_log,
) -> bool:
    """使用 SpineAtlas 转换图集数据为 Spine 3 格式。"""

    try:
        log(f'    > {t("log.spine.converting_atlas", name=atlas_path.name)}')

        atlas: Atlas = ReadAtlasFile(str(atlas_path))
        atlas.version = False

        atlas.ReScale()

        # 复制引用的 PNG 文件到输出目录（原样复制，不缩放）
        for tex in atlas.atlas:
            png_name = tex.png
            src_png = atlas.path / png_name
            dst_png = output_dir / png_name
            if src_png.exists() and src_png.resolve() != dst_png.resolve():
                shutil.copy2(src_png, dst_png)

        # 保存降级后的 atlas 文件
        atlas.path = output_dir
        atlas.SaveAtlas(output_dir / atlas_path.name)
        log(f'    > {t("log.spine.atlas_downgrade_success")}')
        return True
    except Exception as e:
        log(f'    ✗ {t("log.error_detail", error=e)}')
        return False


def unpack_atlas(
    atlas_path: Path,
    output_dir: Path,
    log: LogFunc = no_log,
) -> bool:
    """将 atlas 文件解包为单独的 PNG 帧图片。"""
    try:
        log(f'    > {t("log.spine.unpacking_atlas", name=atlas_path.name)}')

        atlas = ReadAtlasFile(str(atlas_path))
        atlas.ReScale()
        frames_output_dir = output_dir / "images"
        frames_output_dir.mkdir(parents=True, exist_ok=True)

        atlas.SaveFrames(path=str(frames_output_dir), mode='Normal')

        log(f'    > {t("log.spine.atlas_unpack_success", path=frames_output_dir)}')
        return True
    except Exception as e:
        log(f'    ✗ {t("log.spine.atlas_unpack_failed")}: {e}')
        return False


def _build_rename_mapping(
    bundle_png_names: set[str],
    existing_png_stems: set[str],
) -> dict[str, str]:
    """
    根据Bundle中Texture2D的名称与磁盘PNG文件名的差异，构建重命名映射。
    遍历 Bundle 中 name_N 模式的名称，检查磁盘上是否存在旧版 nameN，
    若存在则映射 nameN → name_N。
    返回 {旧stem: 新stem} 的映射（不含 .png 后缀）
    """
    mapping: dict[str, str] = {}

    for bundle_name in bundle_png_names:
        # 在 Bundle 名称中找 _N 后缀模式（如 CH0808_2、CH0808_home_3）
        match = re.match(r'^(.+)_(\d+)$', bundle_name)
        if not match:
            continue
        prefix, number = match.group(1), match.group(2)
        # 旧版导出格式：去掉下划线，如 CH08082、CH0808_home3
        legacy_stem = f"{prefix}{number}"
        if legacy_stem in existing_png_stems and legacy_stem not in bundle_png_names:
            mapping[legacy_stem] = bundle_name

    return mapping


def check_legacy_rename_needed(source_folder_path: Path, bundle_png_names: set[str]) -> bool:
    """
    检测目录中的资源是否需要旧版文件名修正。
    通过对比磁盘PNG文件名与Bundle中Texture2D名称来判断。
    如果检测到需要重命名则返回 True，否则返回 False。
    """
    existing_png_stems = {f.stem for f in source_folder_path.iterdir()
                         if f.is_file() and f.suffix.lower() == '.png'}

    return bool(_build_rename_mapping(bundle_png_names, existing_png_stems))


def normalize_legacy_assets(source_folder_path: Path, bundle_png_names: set[str], log: LogFunc = no_log) -> Path:
    """
    修正旧版 Spine 3.8 文件名格式。
    根据Bundle中Texture2D的名称，将磁盘上不匹配的PNG文件重命名，并同步更新Atlas文件中的引用。
    此函数创建一个临时目录,复制所有文件并在其中进行重命名,不修改用户原始文件。

    Args:
        source_folder_path: 包含待修正文件的目录
        bundle_png_names: Bundle中Texture2D的名称集合（不含后缀）
        log: 日志记录函数

    Returns:
        临时目录路径,包含修正后的文件
    """
    existing_png_stems = {f.stem for f in source_folder_path.iterdir()
                         if f.is_file() and f.suffix.lower() == '.png'}

    stem_mapping = _build_rename_mapping(bundle_png_names, existing_png_stems)

    # 构建 PNG 文件名映射 {old_filename: new_filename}
    png_mapping: dict[str, str] = {f"{old}.png": f"{new}.png" for old, new in stem_mapping.items()}

    # 创建临时目录，复制并重命名
    final_temp_dir = tempfile.mkdtemp(prefix="spine38_fix_")
    final_temp_path = Path(final_temp_dir)

    for source_file in source_folder_path.iterdir():
        if not source_file.is_file():
            continue

        dest_name = png_mapping.get(source_file.name, source_file.name)
        shutil.copy2(source_file, final_temp_path / dest_name)

        if dest_name != source_file.name:
            log(f"  - {t('log.file.rename', old=source_file.name, new=dest_name)}")

    # 更新 Atlas 文件中的 PNG 引用
    for atlas_file in final_temp_path.glob('*.atlas'):
        content = atlas_file.read_text(encoding='utf-8')
        modified = False
        for old_name, new_name in png_mapping.items():
            if old_name in content:
                content = content.replace(old_name, new_name)
                modified = True
        if modified:
            atlas_file.write_text(content, encoding='utf-8')
            log(f"  - {t('log.spine.edit_atlas', filename=atlas_file.name)}")

    return final_temp_path

