# utils.py

import binascii
import os
import re
import shutil
from PIL import Image
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from SpineAtlas import Atlas, ReadAtlasFile, AtlasScale

from i18n import i18n_manager, t

def no_log(message):
    """A dummy logger that does nothing."""
    pass

LogFunc = Callable[[str], None]

class CRCUtils:
    """
    一个封装了CRC32计算和修正逻辑的工具类。
    """

    # --- 公开的静态方法 ---

    @staticmethod
    def compute_crc32(data: bytes) -> int:
        """
        计算数据的标准CRC32 (IEEE)值。
        """
        return binascii.crc32(data) & 0xFFFFFFFF

    @staticmethod
    def check_crc_match(source_1: Path | bytes, source_2: Path | bytes) -> bool:
        """
        检测两个文件或字节数据的CRC值是否匹配。
        返回True表示CRC值一致，False表示不一致。
        """
        if isinstance(source_1, Path):
            with open(str(source_1), "rb") as f:
                data_1 = f.read()
        else:
            data_1 = source_1

        if isinstance(source_2, Path):
            with open(str(source_2), "rb") as f:
                data_2 = f.read()
        else:
            data_2 = source_2

        crc_1 = CRCUtils.compute_crc32(data_1)
        crc_2 = CRCUtils.compute_crc32(data_2)
        
        return crc_1 == crc_2
    
    @staticmethod
    def apply_crc_fix(original_data: bytes, modified_data: bytes, enable_padding: bool = False) -> bytes | None:
        """
        计算修正CRC后的数据。
        如果修正成功，返回修正后的完整字节数据；如果失败，返回None。
        """
        original_crc = CRCUtils.compute_crc32(original_data)
        
        padding_bytes = b'\x08\x08\x08\x08' if enable_padding else b''
        # 计算新数据加上4个空字节的CRC，为修正值留出空间
        modified_crc = CRCUtils.compute_crc32(modified_data + padding_bytes + b'\x00\x00\x00\x00')

        original_bytes = CRCUtils._u32_to_bytes_be(original_crc)
        modified_bytes = CRCUtils._u32_to_bytes_be(modified_crc)

        xor_result = CRCUtils._xor_bytes(original_bytes, modified_bytes)
        reversed_bytes = CRCUtils._reverse_bits_in_bytes(xor_result)
        k = CRCUtils._bytes_to_u32_be(reversed_bytes)

        # CRC32多项式: x^32 + x^26 + ... + 1
        crc32_poly = 0x104C11DB7

        correction_value = CRCUtils._gf_inverse(k, crc32_poly)
        correction_bytes_raw = CRCUtils._u32_to_bytes_be(correction_value)

        # 反转每个字节内的位
        correction_bytes = bytes(CRCUtils._reverse_byte_bits(b) for b in correction_bytes_raw)

        if enable_padding:
            final_data = modified_data + padding_bytes + correction_bytes
        else:
            final_data = modified_data + correction_bytes

        final_crc = CRCUtils.compute_crc32(final_data)
        is_crc_match = (final_crc == original_crc)

        return final_data if is_crc_match else None

    @staticmethod
    def manipulate_crc(original_path: Path, modified_path: Path, enable_padding: bool = False) -> bool:
        """
        修正modified_path文件的CRC，使其与original_path文件匹配。
        此方法封装了apply_crc_fix方法，处理文件的读写操作。
        """
        with open(str(original_path), "rb") as f:
            original_data = f.read()
        with open(str(modified_path), "rb") as f:
            modified_data = f.read()

        corrected_data = CRCUtils.apply_crc_fix(original_data, modified_data, enable_padding)
        
        if corrected_data:
            with open(modified_path, "wb") as f:
                f.write(corrected_data)
            return True
        
        return False

    # --- 内部使用的私有静态方法 ---

    @staticmethod
    def _bytes_to_u32_be(b):
        return int.from_bytes(b, 'big')

    @staticmethod
    def _u32_to_bytes_be(i):
        return i.to_bytes(4, 'big')

    @staticmethod
    def _reverse_bits_in_bytes(b):
        num = CRCUtils._bytes_to_u32_be(b)
        rev = 0
        for i in range(32):
            if (num >> i) & 1:
                rev |= 1 << (31 - i)
        return CRCUtils._u32_to_bytes_be(rev)

    @staticmethod
    def _gf_multiply(a, b):
        result = 0
        while b:
            if b & 1:
                result ^= a
            a <<= 1
            b >>= 1
        return result

    @staticmethod
    def _gf_divide(dividend, divisor):
        if divisor == 0:
            return 0
        quotient = 0
        remainder = dividend
        divisor_bits = divisor.bit_length()
        while remainder.bit_length() >= divisor_bits and remainder != 0:
            shift = remainder.bit_length() - divisor_bits
            quotient |= 1 << shift
            remainder ^= divisor << shift
        return quotient

    @staticmethod
    def _gf_mod(dividend, divisor, n):
        if divisor == 0:
            return dividend
        while dividend != 0 and dividend.bit_length() >= divisor.bit_length():
            shift = dividend.bit_length() - divisor.bit_length()
            dividend ^= divisor << shift
        mask = (1 << n) - 1 if n < 64 else 0xFFFFFFFFFFFFFFFF
        return dividend & mask

    @staticmethod
    def _gf_multiply_modular(a, b, modulus, n):
        product = CRCUtils._gf_multiply(a, b)
        return CRCUtils._gf_mod(product, modulus, n)

    @staticmethod
    def _gf_modular_inverse(a, m):
        if a == 0:
            raise ValueError("Inverse of zero does not exist")
        old_r, r = m, a
        old_s, s = 0, 1
        while r != 0:
            q = CRCUtils._gf_divide(old_r, r)
            old_r, r = r, old_r ^ CRCUtils._gf_multiply(q, r)
            old_s, s = s, old_s ^ CRCUtils._gf_multiply(q, s)
        if old_r != 1:
            raise ValueError("Modular inverse does not exist")
        return old_s

    @staticmethod
    def _gf_inverse(k, poly):
        x32 = 0x100000000
        inverse = CRCUtils._gf_modular_inverse(x32, poly)
        result = CRCUtils._gf_multiply_modular(k, inverse, poly, 32)
        return result

    @staticmethod
    def _xor_bytes(a: bytes, b: bytes) -> bytes:
        return bytes(x ^ y for x, y in zip(a, b))

    @staticmethod
    def _reverse_byte_bits(byte):
        return int('{:08b}'.format(byte)[::-1], 2)

def get_environment_info():
    """Collects and formats key environment details."""
    
    # --- Attempt to import libraries and get their versions ---
    # This approach prevents the script from crashing if a library is not installed.

    try:
        import UnityPy
        unitypy_version = UnityPy.__version__ or "Installed"
    except ImportError:
        unitypy_version = "Not installed"

    try:
        from PIL import Image
        pillow_version = Image.__version__ or "Installed"
    except ImportError:
        pillow_version = "Not installed"

    try:
        import tkinter
        tk_version = tkinter.Tcl().eval('info patchlevel') or "Installed"
    except ImportError:
        tk_version = "Not installed"
    except tkinter.TclError:
        tk_version = "Unknown"

    try:
        import tkinterdnd2
        tkinterdnd2_version = tkinterdnd2.TkinterDnD.TkdndVersion or "Installed"
    except ImportError:
        tkinterdnd2_version = "Not installed"
    except AttributeError:
        tkinterdnd2_version = "Unknown"

    try:
        import importlib.metadata
        tb_version = importlib.metadata.version('ttkbootstrap')
    except ImportError:
        tb_version = "Not installed"
    except (AttributeError, importlib.metadata.PackageNotFoundError):
        tb_version = "Unknown"

    # --- Locale and Encoding Information (crucial for file path/text bugs) ---
    try:
        import locale
        lang_code, encoding = locale.getdefaultlocale()
        system_locale = f"{lang_code} (Encoding: {encoding})"
    except (ValueError, TypeError):
        system_locale = "Could not determine"


    import platform
    import sys

    def _is_admin():
        if sys.platform == 'win32':
            try:
                import ctypes
                return ctypes.windll.shell32.IsUserAnAdmin() != 0
            except (ImportError, AttributeError):
                return False
        return False # 在非Windows系统上不是管理员

    lines: list[str] = []
    lines.append("======== Environment Information ========")

    # --- Available Languages ---
    lines.append("\n--- BA Modding Toolkit ---")
    lines.append(f"Current Language:    {i18n_manager.lang}")
    lines.append(f"Available Languages: {', '.join(i18n_manager.get_available_languages())}")

    # --- System Information ---
    lines.append("\n--- System Information ---")
    lines.append(f"Operating System:    {platform.system()} {platform.release()} ({platform.architecture()[0]})")
    lines.append(f"System Platform:     {sys.platform}")
    lines.append(f"System Locale:       {system_locale}")
    lines.append(f"Filesystem Enc:      {sys.getfilesystemencoding()}")
    lines.append(f"Preferred Enc:       {locale.getpreferredencoding()}")
    
    # --- Python Information ---
    lines.append("\n--- Python Information ---")
    lines.append(f"Python Version:      {sys.version.splitlines()[0]}")
    lines.append(f"Python Executable:   {sys.executable}")
    lines.append(f"Working Directory:   {Path.cwd()}")
    lines.append(f"Running as Admin:    {_is_admin()}")

    # --- Library Versions ---
    lines.append("\n--- Library Versions ---")
    lines.append(f"UnityPy Version:     {unitypy_version}")
    lines.append(f"Pillow Version:      {pillow_version}")
    lines.append(f"Tkinter Version:     {tk_version}")
    lines.append(f"TkinterDnD2 Version: {tkinterdnd2_version}")
    lines.append(f"ttkbootstrap Version:{tb_version}")
    
    lines.append("")

    return "\n".join(lines)

def get_search_resource_dirs(base_game_dir: Path, auto_detect_subdirs: bool = True) -> list[Path]:
    """
    获取游戏资源搜索目录列表。
    """
    if auto_detect_subdirs:
        suffixes = ["",
            "BlueArchive_Data/StreamingAssets/PUB/Resource/GameData/Windows",
            "BlueArchive_Data/StreamingAssets/PUB/Resource/Preload/Windows",
            "GameData/Windows",
            "Preload/Windows",
            "GameData/Android",
            "Preload/Android",
            ]
        return [base_game_dir / suffix for suffix in suffixes]
    else:
        return [base_game_dir]

def is_bundle_file(source: Path | bytes, log = no_log) -> bool:
    """
    通过检查文件或字节数据头部来判断是否为Unity的.bundle文件
    """
    try:
        data: bytes = b''
        if isinstance(source, Path):
            if not source.exists():
                log(f"错误: 文件不存在 -> {source}")
                return False
            with open(str(source), 'rb') as f:
                # 读取文件的前32个字节，足够检测"UnityFS"标识
                data = f.read(32)
        else:
            data = source

        if b"UnityFS" in data[:32]:
            return True
        else:
            return False

    except Exception as e:
        log(f"处理源数据时发生错误: {e}")
        return False


class SpineUtils:
    """Spine 资源转换工具类，支持版本升级和降级。"""

    @staticmethod
    def get_skel_version(source: Path | bytes, log: LogFunc = no_log) -> str | None:
        """
        通过扫描文件或字节数据头部来查找Spine版本号。

        Args:
            source: .skel 文件的 Path 对象或其字节数据 (bytes)。
            log: 日志记录函数

        Returns:
            一个字符串，表示Spine的版本号，例如 "4.2.33"。
            如果未找到，则返回 None。
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

    @staticmethod
    def run_skel_converter(
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

                current_version = SpineUtils.get_skel_version(temp_input_path, log)
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
    def handle_skel_upgrade(
        skel_bytes: bytes,
        resource_name: str,
        enabled: bool = False,
        converter_path: Path | None = None,
        target_version: str | None = None,
        log: LogFunc = no_log,
    ) -> bytes:
        """
        处理 .skel 文件的版本检查和升级。
        如果无需升级或升级失败，则返回原始字节。
        """
        if not enabled or not converter_path or not target_version:
            return skel_bytes

        if not converter_path.exists():
            return skel_bytes

        if target_version.count(".") != 2:
            return skel_bytes

        try:
            log(f'  > {t("log.spine.skel_detected", name=resource_name)}')
            current_version = SpineUtils.get_skel_version(skel_bytes, log)
            target_major_minor = ".".join(target_version.split('.')[:2])

            if current_version and not current_version.startswith(target_major_minor):
                log(f'    > {t("log.spine.version_mismatch_converting", current=current_version, target=target_version)}')

                skel_success, upgraded_content = SpineUtils.run_skel_converter(
                    input_data=skel_bytes,
                    converter_path=converter_path,
                    target_version=target_version,
                    log=log
                )
                if skel_success:
                    log(f'  > {t("log.spine.skel_conversion_success", name=resource_name)}')
                    return upgraded_content
                else:
                    log(f'  ❌ {t("log.spine.skel_conversion_failed_using_original", name=resource_name)}')

        except Exception as e:
            log(f'    ❌ {t("log.error_detail", error=e)}')

        return skel_bytes

    @staticmethod
    def run_atlas_downgrader(
        input_atlas: Path,
        output_dir: Path,
        log: LogFunc = no_log,
    ) -> tuple[bool, list[str]]:
        """使用 SpineAtlas 转换图集数据为 Spine 3 格式。"""
        processed_pngs = []
        try:
            log(f'    > {t("log.spine.converting_atlas", name=input_atlas.name)}')
            
            atlas: Atlas = ReadAtlasFile(str(input_atlas))
            atlas.version = False
            
            for page in atlas.atlas:
                if page.scale != 1.0:
                    log(f'      > {t("log.spine.rescaling_page", page=page.png, scale=page.scale)}')
                    
                    reverse_scale = 1.0 / page.scale
                    AtlasScale(page, reverse_scale, reverse_scale)
                    page.scale = 1.0
                    
                    img_path = input_atlas.parent / page.png
                    if img_path.exists():
                        with Image.open(img_path) as img:
                            w, h = img.size
                            new_w = int(w * reverse_scale)
                            new_h = int(h * reverse_scale)
                            resized_img = img.resize((new_w, new_h), Image.BICUBIC)
                            resized_img.save(output_dir / page.png)
                            page.w = new_w
                            page.h = new_h
                            processed_pngs.append(page.png)
            
            output_path = output_dir / input_atlas.name
            atlas.SaveAtlas(str(output_path))
            return True, processed_pngs
        except Exception as e:
            log(f'      ✗ {t("log.error_detail", error=e)}')
            return False, processed_pngs

    @staticmethod
    def handle_group_downgrade(
        skel_path: Path,
        atlas_path: Path,
        output_dir: Path,
        skel_converter_path: Path,
        target_version: str,
        log: LogFunc = no_log,
    ) -> None:
        """
        处理单个Spine资产组（skel, atlas, pngs）的降级。
        始终尝试进行降级操作。
        """
        version = SpineUtils.get_skel_version(skel_path, log)
        log(f"    > {t('log.spine.version_detected_downgrading', version=version or t('common.unknown'))}")
        with tempfile.TemporaryDirectory() as conv_out_dir_str:
            conv_output_dir = Path(conv_out_dir_str)

            atlas_success, processed_pngs = SpineUtils.run_atlas_downgrader(
                atlas_path, conv_output_dir, log
            )

            if atlas_success:
                log(f'    > {t("log.spine.atlas_downgrade_success")}')
                
                for png_file in atlas_path.parent.glob("*.png"):
                    if png_file.name not in processed_pngs:
                        shutil.copy2(png_file, conv_output_dir / png_file.name)
                
                for converted_file in conv_output_dir.iterdir():
                    shutil.copy2(converted_file, output_dir / converted_file.name)
                    log(f"      - {converted_file.name}")
            else:
                log(f'    ✗ {t("log.spine.atlas_downgrade_failed")}.')

            output_skel_path = output_dir / skel_path.name
            skel_success, _ = SpineUtils.run_skel_converter(
                input_data=skel_path,
                converter_path=skel_converter_path,
                target_version=target_version,
                output_path=output_skel_path,
                log=log
            )
            if not skel_success:
                log(f'    ✗ {t("log.spine.skel_conversion_failed_using_original")}')

    @staticmethod
    def normalize_legacy_spine_assets(source_folder_path: Path, log: LogFunc = no_log) -> Path:
        """
        修正旧版 Spine 3.8 文件名格式
        将类似 CH0808_home2.png 的文件重命名为 CH0808_home_2.png
        并更新 .atlas 文件中的引用
        此函数创建一个临时目录，复制所有文件并在其中进行重命名，不修改用户原始文件。

        Returns:
            临时目录路径，包含修正后的文件
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
                    log(f"  ❌ {t("log.error_detail", error=e)}")

            final_temp_dir = tempfile.mkdtemp(prefix="spine38_fix_")
            final_temp_path = Path(final_temp_dir)

            for item in temp_dir_path.iterdir():
                if item.is_file():
                    shutil.copy2(item, final_temp_path / item.name)

            return final_temp_path

class ImageUtils:
    @staticmethod
    def bleed_image(image: Image.Image, iteration: int = 8) -> Image.Image:
        """
        对图像进行 Bleed 处理。
        """
        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        width, height = image.size
        original_alpha = image.getchannel('A')
        
        # 优化：使用 LUT 代替逐像素操作
        lut = [255] * 256
        lut[0] = 0
        mask = original_alpha.point(lut)

        # 优化：如果没有完全透明像素，直接返回
        if original_alpha.getextrema()[0] > 0:
            return image

        current_canvas = image.copy()
        
        for _ in range(iteration):
            layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            offsets = [(1, 0), (-1, 0), (0, 1), (0, -1)]
            
            for dx, dy in offsets:
                shifted = current_canvas.transform(
                    (width, height),
                    Image.Transform.AFFINE,
                    (1, 0, -dx, 0, 1, -dy)
                )
                layer.alpha_composite(shifted)
            
            layer.alpha_composite(current_canvas)
            current_canvas = layer

        result = Image.composite(image, current_canvas, mask)
        r, g, b, _ = result.split()
        final = Image.merge("RGBA", (r, g, b, original_alpha))

        return final