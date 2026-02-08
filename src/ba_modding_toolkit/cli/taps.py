# cli/taps.py
from argparse import RawTextHelpFormatter
from typing import Literal
from tap import Tap
from pathlib import Path

class BaseTap(Tap):
    """基础Tap类，提供共享配置。"""

    def configure(self) -> None:
        self.description = "BA Modding Toolkit - Command Line Interface."
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True


class UpdateTap(Tap):
    """Update命令的参数解析器 - 用于更新或移植Mod。"""

    # 基本参数
    old: Path  # Path to the old Mod bundle file.
    output_dir: Path = Path('./output/')  # Directory to save the generated Mod file (Default: ./output/).

    # 目标文件定位参数
    target: Path | None = None  # Path to the new game resource bundle file (Overrides --resource-dir if provided).
    resource_dir: Path | None = None  # Path to the game resource directory. Will try to find the directory automatically if not provided.

    # 资源与保存参数
    no_crc: bool = False  # Disable CRC fix function.
    extra_bytes: str | None = None  # Extra bytes in hex format (e.g., "0x08080808" or "QWERTYUI") to append before CRC correction.
    asset_types: list[str] = ['Texture2D', 'TextAsset', 'Mesh']  # List of asset types to replace.
    compression: Literal['lzma', 'lz4', 'original', 'none'] = 'lzma'  # Compression method for Bundle files.

    # Spine转换参数
    enable_spine_conversion: bool = False  # Enable Spine skeleton conversion.
    spine_converter_path: Path | None = None  # Full path to SpineSkeletonDataConverter.exe.
    target_spine_version: str = '4.2.33'  # Target Spine version (e.g., "4.2.33").

    def configure(self) -> None:
        self.description = '''Update or port a Mod, migrating assets from an old Mod to a specific Bundle.
        

Examples:
  # Automatically search for new file and update
  bamt-cli update "C:\\path\\to\\old_mod.bundle"

  # Disable CRC fixing
  bamt-cli update "old_mod.bundle" --no-crc

  # Manually specify new file and update
  bamt-cli update "old_mod.bundle" --target "C:\\path\\to\\new_game_file.bundle" --output-dir "C:\\path\\to\\output"

  # Enable Spine skeleton conversion
  bamt-cli update "old.bundle" --enable-spine-conversion --spine-converter-path "C:\\path\\to\\SpineSkeletonDataConverter.exe" --target-spine-version "4.2.0808"
'''
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True
        self.add_argument('--asset-types', nargs='+', choices=['Texture2D', 'TextAsset', 'Mesh', 'ALL'])
        self.add_argument('old') # 第一个参数，可以匿名


class PackTap(Tap):
    """Pack命令的参数解析器 - 用于资源打包。"""

    # 基本参数
    bundle: Path  # Path to the target bundle file to modify.
    folder: Path  # Path to the folder containing asset files.
    output_dir: Path = Path('./output/')  # Directory to save the modified bundle file.

    # 保存参数
    no_crc: bool = False  # Disable CRC fix function.
    extra_bytes: str | None = None  # Extra bytes in hex format (e.g., "0x08080808" or "QWERTYUI") to append before CRC correction.
    compression: Literal['lzma', 'lz4', 'original', 'none'] = 'lzma'  # Compression method for Bundle files.

    # Spine转换参数
    enable_spine_conversion: bool = False  # Enable Spine skeleton conversion.
    spine_converter_path: Path | None = None  # Full path to SpineSkeletonDataConverter.exe.
    target_spine_version: str = '4.2.33'  # Target Spine version.

    def configure(self) -> None:
        self.description = '''Pack contents from an asset folder into a target bundle file.

Example:
  bamt-cli pack --bundle "C:\\path\\to\\target.bundle" --folder "C:\\path\\to\\assets" --output-dir "C:\\path\\to\\output"
'''
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True


class CrcTap(Tap):
    """CRC命令的参数解析器 - 用于CRC修正工具。"""

    # 基本参数
    modified: Path  # Path to the modified file (to be fixed or calculated).

    # 原始文件定位参数
    original: Path | None = None  # Path to the original file (provides target CRC value).
    resource_dir: Path | None = None  # Path to the game resource directory. Will try to find the directory automatically if not provided.

    # 操作选项
    check_only: bool = False  # Only calculate and compare CRC, do not modify any files.
    no_backup: bool = False  # Do not create a backup (.bak) before fixing the file.
    extra_bytes: str | None = None  # Extra bytes in hex format (e.g., "0x08080808" or "QWERTYUI") to append before CRC correction.

    def configure(self) -> None:
        self.description = '''Tool to fix file CRC32 checksum or calculate/compare CRC32 values.
It OVERWRITES the input file and will NOT output at "output/" directory.

Examples:
  # Fix CRC of my_mod.bundle to match original bundle
  bamt-cli crc "my_mod.bundle"

  # Automatically search original file in game directory and fix CRC
  bamt-cli crc "my_mod.bundle" --resource-dir "C:\\path\\to\\game_data"

  # Check if CRC matches only, do not modify file
  bamt-cli crc "my_mod.bundle" --original "original.bundle" --check-only

  # Calculate CRC for a single file
  bamt-cli crc "my_mod.bundle" --check-only
'''
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True
        self.add_argument('modified') # 第一个参数，可以匿名


class ExtractTap(Tap):
    """Extract命令的参数解析器 - 用于从Bundle中提取资源。"""

    # 基本参数
    bundles: list[Path]  # Path(s) to the bundle file(s) to extract assets from.
    output_dir: Path = Path('./output/')  # Base directory to save the extracted assets.
    subdir: str | None = None  # Subdirectory name within output_dir. Auto-generated from bundle name if not specified.

    # 资源类型参数
    asset_types: list[str] = ['Texture2D', 'TextAsset', 'Mesh']  # List of asset types to extract.

    # Spine转换参数
    enable_spine_downgrade: bool = False  # Enable Spine skeleton downgrade.
    spine_converter_path: Path | None = None  # Full path to SpineSkeletonDataConverter.exe.
    target_spine_version: str = '3.8.75'  # Target Spine version for downgrade (e.g., "3.8.75").

    # Atlas导出参数
    atlas_export_mode: str = 'atlas'  # Atlas export mode: "atlas", "unpack", or "both".

    def configure(self) -> None:
        self.description = '''Extract assets from Unity Bundle files.

Examples:
  # Extract all supported assets from a single bundle
  bamt-cli extract "C:\\path\\to\\bundle.bundle"

  # Extract with Spine downgrade
  bamt-cli extract "bundle.bundle" --enable-spine-downgrade --spine-converter-path "C:\\path\\to\\SpineSkeletonDataConverter.exe" --target-spine-version 3.8.75

  # Extract multiple bundles
  bamt-cli extract "bundle1.bundle" "bundle2.bundle" --output-dir "C:\\output"

  # Extract files at "output/CH0808/"
  bamt-cli extract "CH0808_assets.bundle" --subdir "CH0808"

  # Extract with unpack mode for atlas files
  bamt-cli extract "bundle.bundle" --atlas-export-mode unpack
'''
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True
        self.add_argument('--asset-types', nargs='+', choices=['Texture2D', 'TextAsset', 'Mesh', 'ALL'])
        self.add_argument('--atlas-export-mode', choices=['atlas', 'unpack', 'both'])
        self.add_argument('bundles', nargs='+')  # 一个或多个bundle文件路径


class EnvTap(Tap):
    """Env命令的参数解析器 - 用于显示环境信息。"""

    def configure(self) -> None:
        self.description = 'Display system information and library versions of the current environment.'


class MainTap(BaseTap):
    """主Tap类，包含所有子命令。"""

    def configure(self) -> None:
        super().configure()
        self.add_subparsers(dest='command', help='Available commands')
        self.add_subparser('update', UpdateTap, help='Update or port a Mod, migrating assets from an old Mod to a specific Bundle.')
        self.add_subparser('pack', PackTap, help='Pack contents from an asset folder into a target bundle file.')
        self.add_subparser('extract', ExtractTap, help='Extract assets from Unity Bundle files.')
        self.add_subparser('crc', CrcTap, help='Tool to fix file CRC32 checksum or calculate/compare CRC32 values.')
        self.add_subparser('env', EnvTap, help='Display system information and library versions.')
