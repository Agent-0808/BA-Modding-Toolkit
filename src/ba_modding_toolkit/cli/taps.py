# cli/taps.py
from argparse import RawTextHelpFormatter
from typing import Literal
from tap import Tap

class BaseTap(Tap):
    """基础Tap类，提供共享配置。"""

    def configure(self) -> None:
        self.description = "BA Modding Toolkit - Command Line Interface."
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True


class UpdateTap(Tap):
    """Update命令的参数解析器 - 用于更新或移植Mod。"""

    # 基本参数
    old: str  # Path to the old Mod bundle file.
    output_dir: str = './output/'  # Directory to save the generated Mod file (Default: ./output/).

    # 目标文件定位参数
    target: str | None = None  # Path to the new game resource bundle file (Overrides --resource-dir if provided).
    resource_dir: str | None = None  # Path to the game resource directory. Will try to find the directory automatically if not provided.

    # 资源与保存参数
    no_crc: bool = False  # Disable CRC fix function.
    extra_bytes: str | None = None  # Extra bytes in hex format (e.g., "0x08080808" or "QWERTYUI") to append before CRC correction.
    asset_types: list[str] = ['Texture2D', 'TextAsset', 'Mesh']  # List of asset types to replace.
    compression: Literal['lzma', 'lz4', 'original', 'none'] = 'lzma'  # Compression method for Bundle files.

    # Spine转换参数
    enable_spine_conversion: bool = False  # Enable Spine skeleton conversion.
    spine_converter_path: str | None = None  # Full path to SpineSkeletonDataConverter.exe.
    target_spine_version: str = '4.2.33'  # Target Spine version (e.g., "4.2.33").

    def configure(self) -> None:
        self.description = '''Update or port a Mod, migrating assets from an old Mod to a specific Bundle.

Examples:
  # Automatically search for new file and update
  python maincli.py update --old "C:\\path\\to\\old_mod.bundle" --resource-dir "C:\\path\\to\\GameData\\Windows"

  # Manually specify new file and update
  python maincli.py update --old "C:\\path\\to\\old_mod.bundle" --target "C:\\path\\to\\new_game_file.bundle" --output-dir "C:\\path\\to\\output"

  # Enable Spine skeleton conversion
  python maincli.py update --old "old.bundle" --target "new.bundle" --output-dir "output" --enable-spine-conversion --spine-converter-path "C:\\path\\to\\SpineSkeletonDataConverter.exe" --target-spine-version "4.2.33"
'''
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True
        self.add_argument('--asset-types', nargs='+', choices=['Texture2D', 'TextAsset', 'Mesh', 'ALL'])


class PackTap(Tap):
    """Pack命令的参数解析器 - 用于资源打包。"""

    # 基本参数
    bundle: str  # Path to the target bundle file to modify.
    folder: str  # Path to the folder containing asset files.
    output_dir: str = './output/'  # Directory to save the modified bundle file.

    # 保存参数
    no_crc: bool = False  # Disable CRC fix function.
    compression: Literal['lzma', 'lz4', 'original', 'none'] = 'lzma'  # Compression method for Bundle files.

    # Spine转换参数
    enable_spine_conversion: bool = False  # Enable Spine skeleton conversion.
    spine_converter_path: str | None = None  # Full path to SpineSkeletonDataConverter.exe.
    target_spine_version: str = '4.2.33'  # Target Spine version.

    def configure(self) -> None:
        self.description = '''Pack contents from an asset folder into a target bundle file.

Example:
  python maincli.py pack --bundle "C:\\path\\to\\target.bundle" --folder "C:\\path\\to\\assets" --output-dir "C:\\path\\to\\output"
'''
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True


class CrcTap(Tap):
    """CRC命令的参数解析器 - 用于CRC修正工具。"""

    # 基本参数
    modified: str  # Path to the modified file (to be fixed or calculated).

    # 原始文件定位参数
    original: str | None = None  # Path to the original file (provides target CRC value).
    resource_dir: str | None = None  # Path to the game resource directory. Will try to find the directory automatically if not provided.

    # 操作选项
    check_only: bool = False  # Only calculate and compare CRC, do not modify any files.
    no_backup: bool = False  # Do not create a backup (.bak) before fixing the file.

    def configure(self) -> None:
        self.description = '''Tool to fix file CRC32 checksum or calculate/compare CRC32 values.

Examples:
  # Fix CRC of my_mod.bundle to match original.bundle (Manual)
  python maincli.py crc --modified "my_mod.bundle" --original "original.bundle"

  # Automatically search original file in game directory and fix CRC
  python maincli.py crc --modified "my_mod.bundle" --resource-dir "C:\\path\\to\\game_data"

  # Check if CRC matches only, do not modify file
  python maincli.py crc --modified "my_mod.bundle" --original "original.bundle" --check-only

  # Calculate CRC for a single file
  python maincli.py crc --modified "my_mod.bundle" --check-only
'''
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True


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
        self.add_subparser('crc', CrcTap, help='Tool to fix file CRC32 checksum or calculate/compare CRC32 values.')
        self.add_subparser('env', EnvTap, help='Display system information and library versions.')
