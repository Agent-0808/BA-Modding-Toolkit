# cli/taps.py
from argparse import RawTextHelpFormatter
from tap import Tap, Positional
from pathlib import Path
from typing import Literal

from ..models import ReplaceAssetType, CompressionType, MatchStrategy
from ..report import ReportFormat
from ..utils import BARegion
from ..naming import CharacterInternalIDMap

class BaseTap(Tap):
    """基础Tap类，提供共享配置。"""

    def configure(self) -> None:
        self.description = "BA Modding Toolkit - Command Line Interface."
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True


class UpdateTap(Tap):
    """Update命令的参数解析器 - 用于更新或移植Mod。"""

    # 基本参数
    old: Positional[list[Path]]  # Path(s) to the old Mod bundle file(s).
    output_dir: Path = Path('./output/')  # Directory to save the generated Mod file (Default: ./output/).

    # 目标文件定位参数
    target: list[Path] | None = None  # Path(s) to the new game resource bundle file(s) (Overrides --resource-dir if provided).
    resource_dir: Path | None = None  # Path to the game resource directory. Will try to find the directory automatically if not provided.
    region: BARegion = 'auto'  # Game region used to auto-detect the install path (auto = global first, then japan).

    # 资源与保存参数
    no_crc: bool = False  # Disable CRC fix function.
    extra_bytes: str | None = None  # Extra bytes in hex format (e.g., "0x08080808" or "QWERTYUI") to append before CRC correction.
    asset_types: list[ReplaceAssetType] = ['Texture2D', 'TextAsset', 'Mesh']  # List of asset types to replace.
    compression: CompressionType = 'lzma'  # Compression method for Bundle files.
    save_all: bool = False  # Save all files including unchanged ones (default: skip unchanged files).

    # Spine转换参数
    skel_converter_path: Path | None = None  # Full path to SpineSkeletonDataConverter.exe. Spine conversion is enabled when provided.
    target_spine_version: str = '4.2.33'  # Target Spine version (e.g., "4.2.33").

    # 匹配策略
    strategy: MatchStrategy = 'path_id'  # Match strategy for cross-version migration.

    def configure(self) -> None:
        self.description = '''Update or port a Mod, migrating assets from old Mod(s) to new Bundle(s).

Examples:
  # Automatically search for new file and update single Mod
  bamt-cli update "C:\\path\\to\\old_mod.bundle"

  # Update multiple Mods at once
  bamt-cli update "mod1.bundle" "mod2.bundle" "mod3.bundle"

  # Manually specify target file(s)
  bamt-cli update "old.bundle" --target "new.bundle"
  bamt-cli update "old1.bundle" "old2.bundle" --target "new1.bundle" "new2.bundle"

  # Disable CRC fixing
  bamt-cli update "old_mod.bundle" --no-crc

  # Enable Spine skeleton conversion
  bamt-cli update "old.bundle" --skel-converter-path "C:\\path\\to\\SpineSkeletonDataConverter.exe" --target-spine-version "4.2.0808"
'''
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True


class PackTap(Tap):
    """Pack命令的参数解析器 - 用于资源打包。"""

    # 基本参数
    bundle: list[Path]  # Path(s) to the target bundle file(s) to modify.
    folder: Path  # Path to the folder containing asset files.
    output_dir: Path = Path('./output/')  # Directory to save the modified bundle file(s).

    # 保存参数
    no_crc: bool = False  # Disable CRC fix function.
    extra_bytes: str | None = None  # Extra bytes in hex format (e.g., "0x08080808" or "QWERTYUI") to append before CRC correction.
    compression: CompressionType = 'lzma'  # Compression method for Bundle files.
    save_all: bool = False  # Save all bundles including unchanged ones (default: skip unchanged bundles).

    # Spine转换参数
    skel_converter_path: Path | None = None  # Full path to SpineSkeletonDataConverter.exe. Spine conversion is enabled when provided.
    target_spine_version: str = '4.2.33'  # Target Spine version.

    def configure(self) -> None:
        self.description = '''Pack contents from an asset folder into target bundle files.

Examples:
  # Pack single folder into single bundle
  bamt-cli pack --bundle "target.bundle" --folder "assets_folder" --output-dir "output"

  # Pack single folder into multiple bundles
  bamt-cli pack --bundle "b1.bundle" "b2.bundle" --folder "assets_folder"

  # Pack with Spine conversion
  bamt-cli pack --bundle "target.bundle" --folder "spine_assets" --skel-converter-path "C:\\path\\to\\SpineSkeletonDataConverter.exe" --target-spine-version "4.2.0808"
'''
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True


class CrcTap(Tap):
    """CRC命令的参数解析器 - 用于CRC修正工具。"""

    # 基本参数
    files: Positional[list[Path]]  # Check mode: 1 file to calculate (compare with filename CRC if present), or 2 files to compare. Fix mode: exactly 1 file.

    # 修正参数
    target_crc: str | None = None  # Target CRC32 in hex (e.g., "0xABCD1234"). If omitted, extracted from the filename.

    # 操作选项
    check: bool = False  # Only calculate and compare CRC, do not modify any files.
    no_backup: bool = False  # Do not create a backup (.backup) before fixing the file.
    extra_bytes: str | None = None  # Extra bytes in hex format (e.g., "0x08080808" or "QWERTYUI") to append before CRC correction.

    # 游戏目录搜索参数（仅 check 模式单文件场景使用，可选）
    resource_dir: Path | None = None  # Path to the game resource directory. Search for a same-name file to compare against.
    region: BARegion = 'auto'  # Game region used to auto-detect the install path (auto = global first, then japan). Search only runs when --resource-dir/--region is explicitly provided.

    def configure(self) -> None:
        self.description = '''Tool to fix file CRC32 checksum or calculate/compare CRC32 values.
Fix mode OVERWRITES the input file and will NOT output at "output/" directory.

Examples:
  # Fix CRC of my_mod.bundle (target CRC extracted from the filename)
  bamt-cli crc "my_mod.bundle"

  # Fix CRC with an explicit target value
  bamt-cli crc "my_mod.bundle" --target-crc "0xABCD1234"

  # Calculate CRC of a file (also compares with the CRC in the filename if present)
  bamt-cli crc "my_mod.bundle" --check

  # Compare CRC of two files
  bamt-cli crc "my_mod.bundle" "original.bundle" --check

  # Calculate CRC and additionally compare with the same-name file in the game directory
  bamt-cli crc "my_mod.bundle" --check --resource-dir "C:\\path\\to\\game_data"
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
    asset_types: list[ReplaceAssetType] = ['Texture2D', 'TextAsset', 'Mesh']  # List of asset types to extract.

    # Spine转换参数
    skel_converter_path: Path | None = None  # Full path to SpineSkeletonDataConverter.exe. Spine downgrade is enabled when provided.
    target_spine_version: str = '3.8.75'  # Target Spine version for downgrade (e.g., "3.8.75").

    # Atlas解包参数
    unpack_atlas: bool = False  # Unpack Atlas into individual PNG frames while keeping the original files.

    def configure(self) -> None:
        self.description = '''Extract assets from Unity Bundle files.

Examples:
  # Extract all supported assets from a single bundle
  bamt-cli extract "C:\\path\\to\\bundle.bundle"

  # Extract with Spine downgrade
  bamt-cli extract "bundle.bundle" --skel-converter-path "C:\\path\\to\\SpineSkeletonDataConverter.exe" --target-spine-version 3.8.75

  # Extract multiple bundles
  bamt-cli extract "bundle1.bundle" "bundle2.bundle" --output-dir "C:\\output"

  # Extract files at "output/CH0808/"
  bamt-cli extract "CH0808_assets.bundle" --subdir "CH0808"

  # Extract with unpack mode for atlas files
  bamt-cli extract "bundle.bundle" --unpack-atlas
'''
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True


class EnvTap(Tap):
    """Env命令的参数解析器 - 用于显示环境信息。"""

    def configure(self) -> None:
        self.description = 'Display system information and library versions of the current environment.'

class BatchUpdateTap(Tap):
    """Batch-update命令的参数解析器 - 用于批量更新Mod文件。"""

    # 基本参数
    input_dir: Positional[Path]  # Directory containing old Mod bundle files to update.
    output_dir: Path = Path('./output/')  # Directory to save the generated Mod files.

    # 搜索目录参数
    resource_dir: Path | None = None  # Path to the game resource directory for searching new bundles.
    region: BARegion = 'auto'  # Game region used to auto-detect the install path (auto = global first, then japan).

    # 资源与保存参数
    no_crc: bool = False  # Disable CRC fix function.
    extra_bytes: str | None = None  # Extra bytes in hex format (e.g., "0x08080808" or "QWERTYUI").
    asset_types: list[ReplaceAssetType] = ['Texture2D', 'TextAsset', 'Mesh']  # List of asset types to replace.
    compression: CompressionType = 'lzma'  # Compression method.

    # Spine转换参数
    skel_converter_path: Path | None = None  # Full path to SpineSkeletonDataConverter.exe. Spine conversion is enabled when provided.
    target_spine_version: str = '4.2.33'  # Target Spine version.

    # 匹配策略
    strategy: MatchStrategy = 'path_id'  # Match strategy.
    max_workers: int = 1  # Number of parallel worker threads (1 = sequential).

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
  bamt-cli batch-update "C:\\path\\to\\old_mods\\" --skel-converter-path "C:\\tools\\SpineSkeletonDataConverter.exe" --target-spine-version "4.2.0808"
'''
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True


class ReportTap(Tap):
    """Report命令的参数解析器 - 用于生成Mod列表报告。"""

    # 基本参数
    output_dir: Path = Path('./output/reports/')  # Directory to save the report file.

    # 搜索目录参数
    resource_dir: Path | None = None  # Path to the game resource directory.
    region: BARegion = 'auto'  # Game region used to auto-detect the install path (auto = global first, then japan).

    # Spine渲染参数
    spine_viewer_path: Path | None = None  # Path to SpineViewerCLI.exe. Spine preview rendering is enabled when provided.

    # 角色映射参数
    bacii_path: Path | None = None  # Path to BA-Characters-Internal-ID.csv.
    index_column: str = CharacterInternalIDMap.DEFAULT_INDEX_COLUMN  # CSV column used as the lookup key for character mapping.
    name_field: str = "full_name"  # Character name field to display.

    # 报告格式参数
    format: ReportFormat = 'list'  # Report output format.
    max_workers: int = 1  # Number of parallel worker threads for Spine preview rendering (1 = sequential).

    def configure(self) -> None:
        self.description = '''Generate a report of all modded bundle files in the game directory.

Note: The feature recognizes a "modded" bundle as one that has a trailing byte greater than 0.
      For a game version that CRC check is unnecessary, modded bundles may not be recognized.

Examples:
  # Generate report with auto-detected game directory
  bamt-cli report

  # Generate table format report
  bamt-cli report --format table

  # Generate report with Spine preview images
  bamt-cli report --spine-viewer-path "C:\\path\\to\\SpineViewerCLI.exe"

  # Use character name mapping
  bamt-cli report --bacii-path "C:\\path\\to\\BA-Characters-Internal-ID.csv" --name-field "name_jp"

  # Use a different CSV column as the lookup key
  bamt-cli report --bacii-path "C:\\path\\to\\BA-Characters-Internal-ID.csv" --index-column "student_id" --name-field "name_en"
'''
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True


class BatchPreviewTap(Tap):
    """Batch-preview命令的参数解析器 - 用于批量渲染Spine预览图。"""

    # 基本参数
    spine_viewer_path: Positional[Path]  # Path to SpineViewerCLI.exe.
    output_dir: Path = Path('./output/batch_preview/')  # Directory to save preview images.

    # 搜索目录参数
    resource_dir: Path | None = None  # Path to the game resource directory. Will try to find the directory automatically if not provided.
    region: BARegion = 'auto'  # Game region used to auto-detect the install path (auto = global first, then japan).

    # Spine渲染参数
    preset: Literal['low', 'high'] = 'low'  # Preview render preset.
    categories: list[Literal['spinecharacters', 'spinelobbies', 'spinebackground']] = ['spinecharacters', 'spinelobbies', 'spinebackground']  # Categories to render (default: render all).
    max_workers: int = 1  # Number of parallel worker threads (1 = sequential).

    def configure(self) -> None:
        self.description = '''Batch render Spine preview images for all Spine resources in the game directory.

Note: This command renders ALL Spine resources (not limited to modded files),
      grouped by file prefix. Existing preview images with the same name are overwritten.

Examples:
  # Render previews with auto-detected game directory
  bamt-cli batch-preview "C:\\path\\to\\SpineViewerCLI.exe"

  # Specify game resource directory and high quality preset
  bamt-cli batch-preview "C:\\path\\to\\SpineViewerCLI.exe" --resource-dir "C:\\game\\resources" --preset high

  # Render only characters and lobbies
  bamt-cli batch-preview "C:\\path\\to\\SpineViewerCLI.exe" --categories spinecharacters spinelobbies

  # Render with 4 parallel workers
  bamt-cli batch-preview "C:\\path\\to\\SpineViewerCLI.exe" --max-workers 4
'''
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True


class BackupTap(Tap):
    """Backup命令的参数解析器 - 用于备份Mod文件。"""

    output_dir: Path = Path('./output/backup/')  # Directory to save the backup files.
    resource_dir: Path | None = None  # Path to the game resource directory.
    region: BARegion = 'auto'  # Game region used to auto-detect the install path (auto = global first, then japan).
    yes: bool = False  # Automatically confirm clearing the existing backup directory.

    def configure(self) -> None:
        self.description = '''Backup all modded bundle files from the game directory.

Note: The feature recognizes a "modded" bundle as one that has a trailing byte greater than 0.
      For a game version that CRC check is unnecessary, modded bundles may not be recognized.

Examples:
  # Backup with auto-detected game directory
  bamt-cli backup

  # Backup with custom paths
  bamt-cli backup --resource-dir "C:\\path\\to\\game" --output-dir "C:\\backups"

  # Auto-confirm clearing existing backup directory
  bamt-cli backup --yes
'''
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True


class ParseTap(Tap):
    """Parse命令的参数解析器 - 用于解析Bundle文件名。"""

    # 基本参数
    filenames: Positional[list[Path]]  # Filename(s) or path(s) to parse (only the name part is used).

    # 角色映射参数
    bacii_path: Path | None = None  # Path to BA-Characters-Internal-ID.csv. Character name lookup is enabled when provided.
    index_column: str = CharacterInternalIDMap.DEFAULT_INDEX_COLUMN  # CSV column used as the lookup key for character mapping.
    name_field: str = "full_name"  # Character name field to display.

    def configure(self) -> None:
        self.description = '''Parse BA bundle filename(s) and print the parsed components.

Examples:
  # Parse a single filename (full path is also accepted)
  bamt-cli parse "assets-_mx-spinecharacters-ch0808_spr-mxdependency-textures-2077-08-08_12345678.bundle"

  # Parse multiple filenames
  bamt-cli parse "a.bundle" "b.bundle"

  # Resolve character name from the BACII mapping
  bamt-cli parse "ch0001_spr.bundle" --bacii-path "C:\\path\\to\\BA-Characters-Internal-ID.csv"
'''
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True


class MainTap(BaseTap):
    """主Tap类，包含所有子命令。"""

    # 全局参数（需放在子命令之前，如: bamt-cli --lang en-us update ...）
    lang: str | None = None  # Interface language for localized output (e.g., "en-US", "zh-CN", "debug"; default: auto-detect).

    def configure(self) -> None:
        super().configure()
        self.add_subparsers(dest='command', help='Available commands')
        self.add_subparser('update', UpdateTap, help='Update or port a Mod, migrating assets from an old Mod to a specific Bundle.')
        self.add_subparser('batch-update', BatchUpdateTap, help='Batch update multiple Mod files from an input directory.')
        self.add_subparser('pack', PackTap, help='Pack contents from an asset folder into a target bundle file.')
        self.add_subparser('extract', ExtractTap, help='Extract assets from Unity Bundle files.')
        self.add_subparser('crc', CrcTap, help='Tool to fix file CRC32 checksum or calculate/compare CRC32 values.')
        self.add_subparser('parse', ParseTap, help='Parse BA bundle filename(s) and print the parsed components.')
        self.add_subparser('report', ReportTap, help='Generate a report of all modded bundle files.')
        self.add_subparser('batch-preview', BatchPreviewTap, help='Batch render Spine preview images for all Spine resources.')
        self.add_subparser('backup', BackupTap, help='Backup all modded bundle files.')
        self.add_subparser('env', EnvTap, help='Display system information and library versions.')
