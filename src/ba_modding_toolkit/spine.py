# spine.py

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .i18n import t
from .utils import LogFunc, no_log


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

    @staticmethod
    def atlas_downgrade(
        atlas_path: Path,
        output_dir: Path,
        log: LogFunc = no_log,
    ) -> bool:
        """使用 SpineAtlas 转换图集数据为 Spine 3 格式。"""
        from SpineAtlas import Atlas, ReadAtlasFile
        try:
            log(f'    > {t("log.spine.converting_atlas", name=atlas_path.name)}')

            atlas: Atlas = ReadAtlasFile(str(atlas_path))
            atlas.version = False

            atlas.ReScale()
            atlas.SaveAtlas4_0Scale(outPath=output_dir)
            log(f'    > {t("log.spine.atlas_downgrade_success")}')
            return True
        except Exception as e:
            log(f'    ✗ {t("log.error_detail", error=e)}')
            return False

    @staticmethod
    def unpack_atlas(
        atlas_path: Path,
        output_dir: Path,
        log: LogFunc = no_log,
    ) -> bool:
        """将 atlas 文件解包为单独的 PNG 帧图片。"""
        from SpineAtlas import ReadAtlasFile
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

    @staticmethod
    def normalize_legacy_assets(source_folder_path: Path, log: LogFunc = no_log) -> Path:
        """
        修正旧版 Spine 3.8 文件名格式
        将类似 CH0808_home2.png 的文件重命名为 CH0808_home_2.png
        并更新 .atlas 文件中的引用
        此函数创建一个临时目录,复制所有文件并在其中进行重命名,不修改用户原始文件。

        Returns:
            临时目录路径,包含修正后的文件
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)

            filename_mapping: dict[str, str] = {}

            for source_file in source_folder_path.iterdir():
                if not source_file.is_file():
                    continue

                dest_file = temp_dir_path / source_file.name

                if source_file.suffix.lower() == '.png':
                    old_name = source_file.stem
                    new_name = old_name

                    # TODO: 修复 [CH0144.png] -> [CH014_4.png]
                    match = re.search(r'^(.*)(\d+)$', old_name)
                    if match:
                        prefix = match.group(1)
                        number = match.group(2)
                        new_name = f"{prefix}_{number}"

                    if new_name != old_name:
                        old_filename = source_file.name
                        new_filename = f"{new_name}.png"
                        dest_file = temp_dir_path / new_filename
                        filename_mapping[old_filename] = new_filename
                        log(f"  - {t('log.file.rename', old=old_filename, new=new_filename)}")

                shutil.copy2(source_file, dest_file)

            for atlas_file in temp_dir_path.glob('*.atlas'):
                try:
                    content = atlas_file.read_text(encoding='utf-8')
                    modified = False

                    for old_name, new_name in filename_mapping.items():
                        if old_name in content:
                            content = content.replace(old_name, new_name)
                            modified = True

                    if modified:
                        atlas_file.write_text(content, encoding='utf-8')
                        log(f"  - {t('log.spine.edit_atlas', filename=atlas_file.name)}")

                except Exception as e:
                    log(f"  ❌ {t('log.error_detail', error=e)}")

            final_temp_dir = tempfile.mkdtemp(prefix="spine38_fix_")
            final_temp_path = Path(final_temp_dir)

            for item in temp_dir_path.iterdir():
                if item.is_file():
                    shutil.copy2(item, final_temp_path / item.name)

            return final_temp_path


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


# 为向后兼容保留的 SpineUtils 类别名
class SpineUtils:
    """向后兼容的 SpineUtils 类别名,已弃用,请使用 SkelConverter 或 SpineViewer。"""

    @staticmethod
    def get_skel_version(source: Path | bytes, log: LogFunc = no_log) -> str | None:
        """向后兼容方法,请使用独立的 get_skel_version 函数。"""
        return get_skel_version(source, log)

    @staticmethod
    def run_skel_converter(*args, **kwargs) -> tuple[bool, bytes]:
        """向后兼容方法,请使用 SkelConverter.run()。"""
        return SkelConverter.run(*args, **kwargs)

    @staticmethod
    def handle_skel_upgrade(*args, **kwargs) -> bytes:
        """向后兼容方法,请使用 SkelConverter.upgrade()。"""
        return SkelConverter.upgrade(*args, **kwargs)

    @staticmethod
    def process_skel_downgrade(*args, **kwargs) -> bool:
        """向后兼容方法,请使用 SkelConverter.downgrade()。"""
        return SkelConverter.downgrade(*args, **kwargs)

    @staticmethod
    def process_atlas_downgrade(*args, **kwargs) -> bool:
        """向后兼容方法,请使用 SkelConverter.atlas_downgrade()。"""
        return SkelConverter.atlas_downgrade(*args, **kwargs)

    @staticmethod
    def unpack_atlas_frames(*args, **kwargs) -> bool:
        """向后兼容方法,请使用 SkelConverter.unpack_atlas()。"""
        return SkelConverter.unpack_atlas(*args, **kwargs)

    @staticmethod
    def query_spine_info(*args, **kwargs) -> tuple[bool, dict]:
        """向后兼容方法,请使用 SpineViewer.query()。"""
        return SpineViewer.query(*args, **kwargs)

    @staticmethod
    def render_spine_preview(*args, **kwargs) -> tuple[bool, str]:
        """向后兼容方法,请使用 SpineViewer.render()。"""
        return SpineViewer.render(*args, **kwargs)

    @staticmethod
    def normalize_legacy_spine_assets(*args, **kwargs) -> Path:
        """向后兼容方法,请使用 SkelConverter.normalize_legacy_assets()。"""
        return SkelConverter.normalize_legacy_assets(*args, **kwargs)