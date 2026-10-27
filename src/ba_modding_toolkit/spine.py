# spine.py

import base64
import os
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Literal, Protocol
from SpineAtlas import Atlas, ReadAtlasFile

from .i18n import t
from .utils import CREATE_NO_WINDOW, LogFunc, no_log
from .models import SkelConvertOptions, SkelVersionConflict


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
        input_path: Path,
        output_path: Path | None = None,
        converter_path: Path = None,
        target_version: str = None,
        log: LogFunc = no_log,
    ) -> bool:
        """
        底层转换函数：文件到文件的转换

        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径（None 则覆盖原文件）
            converter_path: 转换器路径
            target_version: 目标版本
            log: 日志函数

        Returns:
            bool: 是否成功
        """
        try:
            # 如果未指定输出路径，则覆盖原文件
            if output_path is None:
                output_path = input_path

            # 获取版本
            current_version = get_skel_version(input_path, log)
            if not current_version:
                log(f'  > ⚠️ {t("log.spine.skel_version_detection_failed")}')
                return False

            # 统一使用临时目录进行转换
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_dir_path = Path(temp_dir)
                temp_input = temp_dir_path / input_path.name
                temp_output = temp_dir_path / f"output_{input_path.name}"

                # 复制输入文件到临时目录
                shutil.copy2(input_path, temp_input)

                command = [
                    str(converter_path),
                    str(temp_input),
                    str(temp_output),
                    "-v",
                    target_version
                ]

                log(f'    > {t("log.spine.converting_skel", name=input_path.name)}')
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
                    # 复制输出文件到目标路径
                    shutil.copy2(temp_output, output_path)
                    return True
                else:
                    log(f'      ✗ {t("log.spine.skel_conversion_failed")}:')
                    log(f"        stdout: {result.stdout.strip()}")
                    log(f"        stderr: {result.stderr.strip()}")
                    return False

        except Exception as e:
            log(f'    ❌ {t("log.error_detail", error=e)}')
            return False

    @staticmethod
    def ensure_version(
        skel_bytes: bytes,
        resource_name: str,
        options: SkelConvertOptions | None = None,
        log: LogFunc = no_log,
    ) -> tuple[bytes, SkelVersionConflict | None]:
        """
        检测 .skel 版本与预设目标版本是否兼容（前两位 major.minor 一致），不一致时尝试转换。

        Args:
            skel_bytes: .skel 文件字节数据
            resource_name: 资源名（用于日志与临时文件名）
            options: Spine 转换选项；target_version 无论转换器是否启用均作为判定基准
            log: 日志函数

        Returns:
            (处理后的字节数据, 冲突信息或 None)；冲突时返回原始字节数据
        """
        target_version = options.target_version if options else None
        if not target_version or target_version.count(".") != 2:
            # 未配置有效的基准版本，不做检测
            return skel_bytes, None

        current_version = get_skel_version(skel_bytes, log)
        if not current_version:
            log(f'  > ⚠️ {t("log.spine.skel_version_detection_failed")}')
            return skel_bytes, None

        major_minor = ".".join(target_version.split(".")[:2])
        if current_version.startswith(major_minor):
            return skel_bytes, None

        # 版本前两位不一致：转换器可用则尝试转换，否则报告冲突
        log(f'  > {t("log.spine.skel_detected", name=resource_name)}')

        if options.enabled and options.converter_path and options.converter_path.exists():
            log(f'    > {t("log.spine.version_mismatch_converting", current=current_version, target=target_version)}')
            converted = SkelConverter._convert_bytes(
                skel_bytes=skel_bytes,
                resource_name=resource_name,
                converter_path=options.converter_path,
                target_version=target_version,
                log=log,
            )
            if converted is not None:
                return converted, None
        else:
            log(f'    > {t("log.spine.version_mismatch_no_convert", current=current_version, target=target_version)}')

        return skel_bytes, SkelVersionConflict(resource_name, current_version, target_version)

    @staticmethod
    def _convert_bytes(
        skel_bytes: bytes,
        resource_name: str,
        converter_path: Path,
        target_version: str,
        log: LogFunc,
    ) -> bytes | None:
        """将 .skel 字节数据转换到目标版本，失败返回 None。"""
        try:
            # 创建临时文件进行转换
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_input_path = Path(temp_dir) / resource_name
                temp_input_path.write_bytes(skel_bytes)

                # 调用 run() 进行转换（原地覆盖）
                success = SkelConverter.run(
                    input_path=temp_input_path,
                    output_path=temp_input_path,
                    converter_path=converter_path,
                    target_version=target_version,
                    log=log
                )

                if success:
                    log(f'  > {t("log.spine.skel_conversion_success")}')
                    return temp_input_path.read_bytes()
                log(f'  ❌ {t("log.spine.skel_conversion_failed")}')

        except Exception as e:
            log(f'    ❌ {t("log.error_detail", error=e)}')

        return None

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
        success = SkelConverter.run(
            input_path=skel_path,
            output_path=output_skel_path,
            converter_path=converter_path,
            target_version=target_version,
            log=log
        )
        if success:
            log(f'    > {t("log.spine.skel_conversion_success", name=skel_path.name)}')
        else:
            log(f'    ✗ {t("log.spine.skel_conversion_failed")}')
        return success


@dataclass(frozen=True)
class RenderOptions:
    """SpineViewerCLI 导出预览图的渲染参数。"""
    fmt: str = "png"
    scale: float = 1.0
    background: str = "#00000000"
    margin: int = 0
    max_resolution: int = 8888
    time: float = 0.0
    quality: int = 100


# 高画质预设：与旧版默认参数一致（extractor / file_list 交互预览使用）
RENDER_PRESET_HIGH = RenderOptions()

# 低画质预设：报告生成使用，降低分辨率与质量以减小体积
RENDER_PRESET_LOW = RenderOptions(max_resolution=1024, quality=50)

# 1x1 透明 PNG：为 spine2dump 的 atlas 页面占位（页面内容不参与列表解析）
_TINY_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def select_animation(animations: list[str], log: LogFunc = no_log) -> str | None:
    """动画选择优先级：Idle_01 > Dummy > 第一个"""
    if "Idle_01" in animations:
        return "Idle_01"
    if "Dummy" in animations:
        return "Dummy"
    if animations:
        log(f'  > {t("log.spine.using_first_animation", anim=animations[0])}')
        return animations[0]
    return None


class SpineBackend(Protocol):
    """Spine 渲染后端接口；SpineViewer 与 Spine2Dump 结构化实现此协议。"""

    def query(
        self,
        skel_path: Path,
        log: LogFunc = no_log,
    ) -> tuple[bool, dict]: ...

    def render(
        self,
        skel_path: Path,
        output_path: Path,
        animation: str,
        render_options: RenderOptions = RENDER_PRESET_HIGH,
        log: LogFunc = no_log,
    ) -> tuple[bool, str]: ...

    def render_preview(
        self,
        skel_path: Path,
        output_path: Path,
        render_options: RenderOptions = RENDER_PRESET_HIGH,
        log: LogFunc = no_log,
    ) -> tuple[bool, str]: ...


def _link_or_copy(src: Path, dst: Path) -> None:
    """优先硬链接（同卷零拷贝），失败时回退复制。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


class SpineViewer:
    """SpineViewerCLI 工具集成类,用于查询信息和渲染预览。"""

    @staticmethod
    def query(
        skel_path: Path,
        viewer_path: Path,
        log: LogFunc = no_log,
    ) -> tuple[bool, dict]:
        """
        查询 Spine skel 文件中的动画和皮肤信息。

        Args:
            skel_path: skel 文件路径
            viewer_path: SpineViewerCLI 可执行文件路径
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
                return False, {"error": result.stderr.strip() or result.stdout.strip()}

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
    def render_preview(
        skel_path: Path,
        output_path: Path,
        viewer_path: Path,
        render_options: RenderOptions = RENDER_PRESET_HIGH,
        log: LogFunc = no_log,
    ) -> tuple[bool, str]:
        """
        从 skel 文件自动选择动画并渲染预览图。

        流程：
        1. 查询动画信息
        2. 选择动画（优先 Idle_01 > Dummy > 第一个）
        3. 查找同目录下的 atlas 文件
        4. 渲染预览图

        Args:
            skel_path: skel 文件路径（atlas 和 png 在同目录）
            output_path: 输出图片路径
            viewer_path: SpineViewerCLI 路径
            render_options: 渲染参数（默认高画质）
            log: 日志函数

        Returns:
            tuple[bool, str]: (是否成功, 状态消息)
        """
        # 查找同目录下的 atlas 文件
        atlas_path = None
        for atlas in skel_path.parent.glob("*.atlas"):
            if atlas.stem == skel_path.stem:
                atlas_path = atlas
                break

        # 查询动画信息
        success, info = SpineViewer.query(skel_path, viewer_path, log)
        if not success:
            return False, f'{t("log.spine.query_failed")}: {info.get("error", "")}'.rstrip(": ")

        # 选择动画（优先 Idle_01 > Dummy > 第一个）
        animation = None
        animations = info.get('animations', [])
        if 'Idle_01' in animations:
            animation = 'Idle_01'
        elif 'Dummy' in animations:
            animation = 'Dummy'
        elif animations:
            animation = animations[0]
            log(f'  > {t("log.spine.using_first_animation", anim=animation)}')

        if not animation:
            log(f'  ⚠️ {t("log.spine.no_animation_found", name=skel_path.name)}')
            return False, t("log.spine.no_animation_found", name=skel_path.name)

        # 渲染预览图
        return SpineViewer.render(
            skel_path=skel_path,
            output_path=output_path,
            viewer_path=viewer_path,
            atlas_path=atlas_path,
            animation=animation,
            render_options=render_options,
            log=log
        )

    @staticmethod
    def render(
        skel_path: Path,
        output_path: Path,
        viewer_path: Path,
        atlas_path: Path | None = None,
        animation: str = "Idle_01",
        skin: str = "",
        render_options: RenderOptions = RENDER_PRESET_HIGH,
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
            render_options: 渲染参数（含输出格式与画质相关参数）
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
                "-f", render_options.fmt,
                "-o", str(output_path),
                "-a", animation,
                "--scale", str(render_options.scale),
                "--color", render_options.background,
                "--margin", str(render_options.margin),
                "--max-resolution", str(render_options.max_resolution),
                "--time", str(render_options.time),
                "--quality", str(render_options.quality),
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


class Spine2Dump:
    """spine2dump 工具集成类，实现与 SpineViewer 相同的渲染后端接口。

    输入是"目录"而非单个 skel，且多 skel 目录会被工具一次性加载，
    因此 query/render 前先把目标骨架隔离到临时目录（skel + atlas + 引用 png）。
    """

    def __init__(self, tool_path: Path):
        self.tool_path = tool_path

    def _find_atlas(self, skel_path: Path) -> Path | None:
        """查找与 skel 同名的 atlas 文件。"""
        for atlas in skel_path.parent.glob("*.atlas"):
            if atlas.stem == skel_path.stem:
                return atlas
        return None

    @contextmanager
    def _isolate_assets(self, skel_path: Path, log: LogFunc = no_log) -> Iterator[Path]:
        """把目标 skel、同名 atlas 及 atlas 引用的 png 复制到临时目录。"""
        with tempfile.TemporaryDirectory(prefix="spine2dump_") as temp_dir:
            work_dir = Path(temp_dir)
            _link_or_copy(skel_path, work_dir / skel_path.name)

            atlas_path = self._find_atlas(skel_path)
            if atlas_path is not None:
                _link_or_copy(atlas_path, work_dir / atlas_path.name)
                try:
                    atlas: Atlas = ReadAtlasFile(str(atlas_path))
                    for tex in atlas.atlas:
                        rel_path = Path(tex.png)
                        src_png = atlas_path.parent / rel_path
                        if src_png.is_file():
                            _link_or_copy(src_png, work_dir / rel_path)
                except Exception as e:
                    # atlas 解析失败时不阻断，交由工具自身报告缺失页面
                    log(f'  ⚠️ {t("log.error_detail", error=e)}')

            yield work_dir

    @staticmethod
    def _parse_inspect(output: str) -> dict:
        """解析 inspect 表格输出中的 Animations / Skins 区段。"""
        info: dict[str, list[str]] = {"animations": [], "skins": []}
        section: str | None = None

        for raw_line in output.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()

            if stripped.startswith("Animations ("):
                section = "animations"
                continue
            if stripped.startswith("Skins ("):
                section = "skins"
                continue
            if stripped.startswith("Expression candidates"):
                section = None
                continue

            if section == "animations" and stripped.startswith("│"):
                cells = [cell.strip() for cell in stripped.strip("│").split("│")]
                if cells and cells[0] and cells[0] != "name":
                    info["animations"].append(cells[0])
            elif section == "skins" and line == stripped:
                # 仅取深度 0 的皮肤行（├─ / └─），排除缩进的附件明细
                if stripped.startswith(("├─ ", "└─ ")):
                    info["skins"].append(stripped[3:].strip())

        return info

    def query(
        self,
        skel_path: Path,
        log: LogFunc = no_log,
    ) -> tuple[bool, dict]:
        """查询 Spine skel 文件中的动画和皮肤信息。"""
        if not skel_path.exists():
            log(f'  ❌ {t("log.file.not_exist", path=skel_path)}')
            return False, {}

        if not self.tool_path.exists():
            log(f'  ❌ {t("log.file.not_exist", path=self.tool_path)}')
            return False, {}

        try:
            log(f'  > {t("log.spine.querying_info", name=skel_path.name)}')
            with self._isolate_assets(skel_path, log) as work_dir:
                result = subprocess.run(
                    [str(self.tool_path), "inspect", str(work_dir)],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='ignore',
                    creationflags=CREATE_NO_WINDOW,
                )

            if result.returncode != 0:
                log(f'  ✗ {t("log.spine.query_failed")}: {result.stderr.strip()}')
                return False, {"error": result.stderr.strip() or result.stdout.strip()}

            info = self._parse_inspect(result.stdout)
            log(f'  > {t("log.spine.query_success", anim_count=len(info["animations"]), skin_count=len(info["skins"]))}')
            return True, info

        except Exception as e:
            log(f'  ❌ {t("log.error_detail", error=e)}')
            return False, {}

    def render(
        self,
        skel_path: Path,
        output_path: Path,
        animation: str,
        render_options: RenderOptions = RENDER_PRESET_HIGH,
        log: LogFunc = no_log,
    ) -> tuple[bool, str]:
        """渲染单帧预览图并移动到 output_path（透明背景 PNG）。

        RenderOptions 仅使用 max_resolution（映射为正方形画布 + --trim），
        fmt/quality/margin/background/time/skin 在该后端下静默忽略。
        """
        if not skel_path.exists():
            msg = t("log.file.not_exist", path=skel_path)
            log(f'  ❌ {msg}')
            return False, msg

        if not self.tool_path.exists():
            msg = t("log.file.not_exist", path=self.tool_path)
            log(f'  ❌ {msg}')
            return False, msg

        try:
            size = max(1, render_options.max_resolution)
            log(f'  > {t("log.spine.rendering_preview", name=skel_path.name, anim=animation)}')

            with self._isolate_assets(skel_path, log) as work_dir:
                dump_dir = work_dir / "dump"
                result = subprocess.run(
                    [
                        str(self.tool_path),
                        "dump",
                        str(work_dir),
                        "-o", str(dump_dir),
                        "--animation", animation,
                        "--start", "0",
                        "--end", "0.0333",
                        "--fps", "1",
                        "--size", str(size),
                        "--trim",
                        "--compression", "fast",
                    ],
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

                frame = dump_dir / animation / "frame_00000.png"
                if not frame.exists():
                    frame = next(dump_dir.glob("*/frame_00000.png"), None)
                if frame is None:
                    msg = t("log.spine.render_file_not_found")
                    log(f'  ✗ {msg}')
                    return False, msg

                output_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(frame), str(output_path))

            if output_path.exists():
                msg = t("log.spine.render_success", path=output_path)
                log(f'  ✓ {msg}')
                return True, msg

            msg = t("log.spine.render_file_not_found")
            log(f'  ✗ {msg}')
            return False, msg

        except Exception as e:
            msg = t("log.error_detail", error=e)
            log(f'  ❌ {msg}')
            return False, msg

    def render_preview(
        self,
        skel_path: Path,
        output_path: Path,
        render_options: RenderOptions = RENDER_PRESET_HIGH,
        log: LogFunc = no_log,
    ) -> tuple[bool, str]:
        """从 skel 文件自动选择动画并渲染预览图。"""
        success, info = self.query(skel_path, log)
        if not success:
            return False, f'{t("log.spine.query_failed")}: {info.get("error", "")}'.rstrip(": ")

        animation = select_animation(info.get('animations', []), log)
        if not animation:
            log(f'  ⚠️ {t("log.spine.no_animation_found", name=skel_path.name)}')
            return False, t("log.spine.no_animation_found", name=skel_path.name)

        return self.render(skel_path, output_path, animation, render_options, log)


def get_spine_backend(backend: Literal["spine_viewer", "spine2dump"], tool_path: Path) -> SpineBackend:
    """按后端名称创建实例；tool_path 为该后端对应的可执行文件路径。"""
    if backend == "spine2dump":
        return Spine2Dump(tool_path)
    return SpineViewer(tool_path)


def atlas_downgrade(
    atlas_path: Path,
    output_dir: Path,
    scale_atlas: bool = False,
    log: LogFunc = no_log,
) -> bool:
    """使用 SpineAtlas 转换图集数据为 Spine 3 格式。

    Args:
        atlas_path: atlas 文件路径
        output_dir: 输出目录
        scale_atlas: 是否根据 scale 缩放（True=使用SaveAtlas4_0Scale，False=手动复制PNG）
        log: 日志函数
    """

    try:
        log(f'    > {t("log.spine.converting_atlas", name=atlas_path.name)}')

        atlas: Atlas = ReadAtlasFile(str(atlas_path))
        atlas.version = False

        atlas.ReScale()

        if scale_atlas:
            # 使用 SaveAtlas4_0Scale，自动缩放 PNG
            atlas.SaveAtlas4_0Scale(outPath=output_dir)
        else:
            # 手动复制 PNG 文件（原样复制，不缩放）
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


def check_skel_animation_diff(
    source_skel: Path | bytes,
    target_skel: Path | bytes,
    viewer_path: Path,
    log: LogFunc = no_log,
) -> list[str]:
    """
    比较两个 skel 的动画差异，返回目标中有但来源中没有的动画列表。

    Args:
        source_skel: 来源 skel 文件路径或内容
        target_skel: 目标 skel 文件路径或内容
        viewer_path: SpineViewerCLI 路径
        log: 日志记录函数

    Returns:
        目标中有但来源中没有的动画名称列表，查询失败时返回空列表
    """
    if not viewer_path or not viewer_path.exists():
        return []

    try:
        with tempfile.TemporaryDirectory(prefix="skel_diff_") as temp_dir:
            temp_path = Path(temp_dir)

            # 统一转为文件路径供 CLI 使用
            def to_file(data: Path | bytes, name: str) -> Path:
                if isinstance(data, Path):
                    return data
                p = temp_path / name
                p.write_bytes(data)
                return p

            src_file = to_file(source_skel, "source.skel")
            tgt_file = to_file(target_skel, "target.skel")

            src_ok, src_info = SpineViewer.query(src_file, viewer_path, log=log)
            tgt_ok, tgt_info = SpineViewer.query(tgt_file, viewer_path, log=log)

            if not (src_ok and tgt_ok):
                return []

            src_anims = set(src_info.get('animations', []))
            tgt_anims = set(tgt_info.get('animations', []))
            return sorted(tgt_anims - src_anims)

    except Exception as e:
        log(f'  ⚠️ {t("log.spine.anim_check_failed", error=e)}')
        return []

