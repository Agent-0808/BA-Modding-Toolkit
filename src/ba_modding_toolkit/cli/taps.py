# cli/taps.py
from argparse import RawTextHelpFormatter
from typing import Literal
from tap import Tap, Positional
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
    old: Positional[Path]  # Path to the old Mod bundle file.
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
    modified: Positional[Path]  # Path to the modified file (to be fixed or calculated).

    # 原始文件定位参数
    original: Path | None = None  # Path to the original file (provides target CRC value).
    resource_dir: Path | None = None  # Path to the game resource directory. Will try to find the directory automatically if not provided.

    # 操作选项
    check_only: bool = False  # Only calculate and compare CRC, do not modify any files.
    no_backup: bool = False  # Do not create a backup (.backup) before fixing the file.
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


class ExtractTap(Tap):
    """Extract命令的参数解析器 - 用于从Bundle中提取资源。"""

    # 基本参数
    bundles: Positional[list[Path]]  # Path(s) to the bundle file(s) to extract assets from.
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


class EnvTap(Tap):
    """Env命令的参数解析器 - 用于显示环境信息。"""

    def configure(self) -> None:
        self.description = 'Display system information and library versions of the current environment.'


class SplitTap(Tap):
    """Split命令的参数解析器 - 将legacy bundle资源拆分到多个modern bundle中。"""

    # 基本参数
    legacy: Positional[Path]  # Path to the legacy bundle file (source of assets).
    output_dir: Path = Path('./output/')  # Directory to save the converted bundle files.

    # Modern files输入方式（二选一）
    modern_files: list[Path] | None = None  # One or more modern bundle file paths.
    resource_dir: Path | None = None  # Directory containing modern bundle files (auto-search by filename prefix).

    # 资源与保存参数
    no_crc: bool = False  # Disable CRC fix function.
    extra_bytes: str | None = None  # Extra bytes in hex format (e.g., "0x08080808" or "QWERTYUI").
    asset_types: list[str] = ['Texture2D', 'TextAsset', 'Mesh']  # List of asset types to replace.
    compression: Literal['lzma', 'lz4', 'original', 'none'] = 'lzma'  # Compression method.

    def configure(self) -> None:
        self.description = '''Split assets from legacy bundle into multiple modern bundles.

This command extracts assets from the legacy bundle and distributes them to matching
assets in the modern bundle files (one-to-many conversion).

Examples:
  # Use directory auto-search for modern files
  bamt-cli split "legacy.bundle" --resource-dir "C:\\path\\to\\modern_files\\"

  # Specify multiple modern files directly
  bamt-cli split "legacy.bundle" --modern-files "sep1.bundle" "sep2.bundle" "sep3.bundle"

  # Specify output directory
  bamt-cli split "legacy.bundle" --resource-dir "./modern/" --output-dir "./output/"

  # Disable CRC fixing
  bamt-cli split "legacy.bundle" --resource-dir "./modern/" --no-crc

  # Specify asset types
  bamt-cli split "legacy.bundle" --resource-dir "./modern/" --asset-types Texture2D TextAsset
'''
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True
        self.add_argument('--asset-types', nargs='+', choices=['Texture2D', 'TextAsset', 'Mesh', 'ALL'])
        self.add_argument('--modern-files', nargs='+', help='One or more modern bundle file paths')


class MergeTap(Tap):
    """Merge命令的参数解析器 - 将多个modern bundle资源合并到legacy bundle中。"""

    # 基本参数
    legacy: Positional[Path]  # Path to the legacy bundle file (to be modified).
    output_dir: Path = Path('./output/')  # Directory to save the merged bundle file.

    # Modern files输入方式（二选一）
    modern_files: list[Path] | None = None  # One or more modern bundle file paths.
    resource_dir: Path | None = None  # Directory containing modern bundle files (auto-search by filename prefix).

    # 资源与保存参数
    no_crc: bool = False  # Disable CRC fix function.
    extra_bytes: str | None = None  # Extra bytes in hex format (e.g., "0x08080808" or "QWERTYUI").
    asset_types: list[str] = ['Texture2D', 'TextAsset', 'Mesh']  # List of asset types to replace.
    compression: Literal['lzma', 'lz4', 'original', 'none'] = 'lzma'  # Compression method.

    def configure(self) -> None:
        self.description = '''Merge assets from multiple modern bundles into legacy bundle.

This command extracts assets from modern bundle files and merges them into
the legacy bundle file (many-to-one conversion).

Examples:
  # Use directory auto-search for modern files
  bamt-cli merge "legacy.bundle" --resource-dir "C:\\path\\to\\modern_files\\"

  # Specify multiple modern files directly
  bamt-cli merge "legacy.bundle" --modern-files "mod1.bundle" "mod2.bundle"

  # Specify output directory
  bamt-cli merge "legacy.bundle" --resource-dir "./modern/" --output-dir "./output/"

  # Disable CRC fixing
  bamt-cli merge "legacy.bundle" --resource-dir "./modern/" --no-crc

  # Specify asset types
  bamt-cli merge "legacy.bundle" --resource-dir "./modern/" --asset-types Texture2D TextAsset
'''
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True
        self.add_argument('--asset-types', nargs='+', choices=['Texture2D', 'TextAsset', 'Mesh', 'ALL'])
        self.add_argument('--modern-files', nargs='+', help='One or more modern bundle file paths')


class BatchUpdateTap(Tap):
    """Batch-update命令的参数解析器 - 用于批量更新Mod文件。"""

    # 基本参数
    input_dir: Positional[Path]  # Directory containing old Mod bundle files to update.
    output_dir: Path = Path('./output/')  # Directory to save the generated Mod files.

    # 搜索目录参数
    resource_dir: Path | None = None  # Path to the game resource directory for searching new bundles.

    # 资源与保存参数
    no_crc: bool = False  # Disable CRC fix function.
    extra_bytes: str | None = None  # Extra bytes in hex format (e.g., "0x08080808" or "QWERTYUI").
    asset_types: list[str] = ['Texture2D', 'TextAsset', 'Mesh']  # List of asset types to replace.
    compression: Literal['lzma', 'lz4', 'original', 'none'] = 'lzma'  # Compression method.

    # Spine转换参数
    enable_spine_conversion: bool = False  # Enable Spine skeleton conversion.
    spine_converter_path: Path | None = None  # Full path to SpineSkeletonDataConverter.exe.
    target_spine_version: str = '4.2.33'  # Target Spine version.

    def configure(self) -> None:
        self.description = '''Batch update multiple Mod files, migrating assets from old Mods to new game bundles.

This command scans the input directory for .bundle files, automatically finds corresponding
new game bundles in the resource directory, and updates them all in batch.

Examples:
  # Batch update all bundles in a directory
  bamt-cli batch-update "C:\\path\\to\\old_mods\\"

  # Specify resource directory for auto-search
  bamt-cli batch-update "C:\\path\\to\\old_mods\\" --resource-dir "C:\\game\\resources"

  # Disable CRC fixing
  bamt-cli batch-update "C:\\path\\to\\old_mods\\" --no-crc

  # Enable Spine conversion
  bamt-cli batch-update "C:\\path\\to\\old_mods\\" --enable-spine-conversion --spine-converter-path "C:\\tools\\SpineSkeletonDataConverter.exe"
'''
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True
        self.add_argument('--asset-types', nargs='+', choices=['Texture2D', 'TextAsset', 'Mesh', 'ALL'])


class BatchLegacyTap(Tap):
    """Batch-legacy命令的参数解析器 - 用于批量将旧版国际服文件转换为新版。"""

    # 基本参数
    input_dir: Positional[Path]  # Directory containing legacy bundle files to convert.
    output_dir: Path = Path('./output/')  # Directory to save the converted bundle files.

    # 搜索目录参数
    resource_dir: Path | None = None  # Path to the game resource directory for searching modern bundles.

    # 资源与保存参数
    no_crc: bool = False  # Disable CRC fix function.
    extra_bytes: str | None = None  # Extra bytes in hex format (e.g., "0x08080808" or "QWERTYUI").
    asset_types: list[str] = ['Texture2D', 'TextAsset', 'Mesh']  # List of asset types to replace.
    compression: Literal['lzma', 'lz4', 'original', 'none'] = 'lzma'  # Compression method.

    def configure(self) -> None:
        self.description = '''Batch convert legacy (old) Global server bundles to modern format.

This command scans the input directory for .bundle files, automatically finds corresponding
modern Global server bundles in the resource directory, and converts them all in batch.

Examples:
  # Batch convert all legacy bundles in a directory
  bamt-cli batch-legacy "C:\\path\\to\\legacy_mods\\"

  # Specify resource directory for auto-search
  bamt-cli batch-legacy "C:\\path\\to\\legacy_mods\\" --resource-dir "C:\\game\\resources"

  # Disable CRC fixing
  bamt-cli batch-legacy "C:\\path\\to\\legacy_mods\\" --no-crc
'''
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True
        self.add_argument('--asset-types', nargs='+', choices=['Texture2D', 'TextAsset', 'Mesh', 'ALL'])


class MainTap(BaseTap):
    """主Tap类，包含所有子命令。"""

    def configure(self) -> None:
        super().configure()
        self.add_subparsers(dest='command', help='Available commands')
        self.add_subparser('update', UpdateTap, help='Update or port a Mod, migrating assets from an old Mod to a specific Bundle.')
        self.add_subparser('batch-update', BatchUpdateTap, help='Batch update multiple Mod files from an input directory.')
        self.add_subparser('merge', MergeTap, help='Merge assets from multiple reference bundles into base bundle (many-to-one).')
        self.add_subparser('split', SplitTap, help='Split assets from base bundle into multiple reference bundles (one-to-many).')
        self.add_subparser('batch-legacy', BatchLegacyTap, help='Batch convert legacy Global bundles to modern format (batch process for split).')
        self.add_subparser('pack', PackTap, help='Pack contents from an asset folder into a target bundle file.')
        self.add_subparser('extract', ExtractTap, help='Extract assets from Unity Bundle files.')
        self.add_subparser('crc', CrcTap, help='Tool to fix file CRC32 checksum or calculate/compare CRC32 values.')
        self.add_subparser('env', EnvTap, help='Display system information and library versions.')
