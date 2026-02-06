<div align="center" style="text-align:center">
  <p>
    <img alt="BAMT icon" src=https://github.com/Agent-0808/BA-Modding-Toolkit/blob/99332127fc5478e227a37d60bad12074c9472992/docs/title.png?raw=true/>
  </p>
  <p>
    <img alt="GitHub License" src="https://img.shields.io/github/license/Agent-0808/BA-Modding-Toolkit">
    <img alt="GitHub Release" src="https://img.shields.io/github/v/release/Agent-0808/BA-Modding-Toolkit">
    <img alt="GitHub Repo stars" src="https://img.shields.io/github/stars/Agent-0808/BA-Modding-Toolkit?style=flat">
    <img alt="GitHub Downloads (all assets, all releases)" src="https://img.shields.io/github/downloads/Agent-0808/BA-Modding-Toolkit/total">
  </p>
</div>

# BA Modding Toolkit

> English Translations are available now. If you find any errors or have any suggestions, please feel free to submit an issue or pull request.

[简体中文](README_zh-CN.md) | English

A toolkit based on UnityPy for automating the creation and updating of Blue Archive/ブルーアーカイブ mods.

Supports Steam version (PC) and other versions (Global/JP server, PC/Android/iOS).

## Introduction

![Abnormal Client](docs/help/abnormal-en.png)

- Downloaded a mod from the internet, replaced the corresponding file in the game directory, but the game shows "Abnormal Client" and cannot login?
- Downloaded a mod released a long time ago, but the filename is different from the latest version? Even after replacement, the character image doesn't change/doesn't display at all/game freezes?
- Want to create your own mod to replace character illustrations, but don't have Unity knowledge?
- Want to unpack game resources and extract character illustrations or other assets?

BA Modding Toolkit can help you solve the above problems, with completely foolproof operations, no need to manually manipulate bundle files.

## Getting Started

You can download the latest version of the executable file from the [Releases](https://github.com/Agent-0808/BA-Modding-Toolkit/releases) page, and double-click to run the program.

## Program Functionalities

The program contains multiple functional tabs:

- **Mod Update**: Update or port Mod files between different platforms
  - **Single Update**: Update a single Mod file
  - **Batch Update**: Batch process multiple Mod files
- **CRC Tool**: CRC checksum correction functionality
- **Asset Packer**: Pack asset files from a folder into a Bundle file, replacing the corresponding assets in the Bundle
- **Asset Extractor**: Extract specified types of assets from Bundle files
- **JP/GL Conversion**: Convert between JP server format and Global server format

## How to Use

### Settings

- Click the **Settings** button at the top of the main interface to open the settings window, configure the game root directory and output directory.
- Click the "Save" button to save the configuration, which will be automatically restored upon next startup.

![How to update a mod with BAMT GUI](docs/help/gui-help-mod-update-en.png)

### Mod Update

#### Single Update

1. Drag and drop or browse to select the old Mod Bundle file that needs to be updated
2. The program will automatically find the corresponding target Bundle file in the resource directory
3. Click the "Update" button, the program will automatically process and generate the updated Bundle file
4. (Optional) After success, click "Overwrite" to apply the modifications. Please ensure the "Create Backup" option is enabled to prevent risks.

If the mod is for the Steam version, please check the "CRC Correction" option.


This feature can also be used to port mods between different platforms, just select the Bundle file from the corresponding platform in step 2.

#### 批量更新 (Batch Update)

1. Drag and drop or browse to select a folder containing multiple Mod files, or directly drag and drop multiple Mod files
2. The program will automatically identify and list all processable Mod files
3. Configure asset types and other options in the settings window
4. Click the "Start" button, the program will process all selected Mod files in sequence

### CRC Tool

1. Drag and drop or browse to select the target Bundle file that needs to be modified
2. The program will automatically find the corresponding original Bundle file in the resource directory
3. Click the "Correct" button: automatically corrects the Bundle file's CRC checksum
4. (Optional) After success, click "Overwrite" to apply the modifications. Please ensure the "Create Backup" option is enabled to prevent risks.

The "Calculate" button can be used to manually view the CRC checksum of a single file or two files.

### Asset Extractor

1. Drag and drop or browse to select the Bundle file to extract assets from
2. Select an output directory, the program will automatically create a subdirectory named after the Bundle file
3. (Optional) In the settings window, configure `SpineSkeletonDataConverter.exe` program path, and enable "Enable Spine Downgrade" option. If enabled, the program will automatically call the third-party program to convert the Spine files to Spine 3.8 format in the extraction process.
4. Click the "Extract" button, the program will extract the assets.

This feature is for extracting assets from existing Bundle files for modification or preview.

Supported asset types: `Texture2D` (`.png`), `TextAsset`(`.skel`、`.atlas`)

### Asset Packer

1. Drag and drop or browse to select the folder containing assets to be packed
    - Supported file types: `.png` (textures), `.skel`, `.atlas` (Spine animation files)
    - Ensure asset filenames match the asset names in the target Bundle file
2. Drag and drop or browse to select the target Bundle file that needs to be modified
3. Click the "Pack" button: performs the asset packing operation
4. (Optional) After success, click "Overwrite" to apply the modifications. Please ensure the "Create Backup" option is enabled to prevent risks.

This feature is for creating new Mods, such as quickly packaging modified assets into Bundle files.

#### Example

Assume you are creating a mod for character `CH0808`, and you have extracted the related illustration assets to a `texture` folder using the "Asset Extractor" feature. This directory should contain the following files:

- CH0808_spr.png
- CH0808_spr.atlas
- CH0808_spr.skel

After modifying these files, you can package them into a Bundle file using the "Asset Packer" feature.

Drag the `texture` folder to the first input box of the interface, and drag the corresponding Bundle file (e.g., `*-spinecharacters-ch0808_spr-*.bundle`) to the second input box of the program, then click the "开始打包" (Start Packing) button to generate a new Bundle file.

This will replace the assets with the same name in the target Bundle with the `*.png`, `*.skel`, and `*.atlas` files from the `texture` folder.

### JP/GL Conversion

Conversion between JP server format (two separate Bundle files) and Global server format (one Bundle file) for a mod that modified the Spine assets.

1. Select the conversion direction at the top of the page (JP -> Global or Global -> JP)
2. Select the Global server Bundle file (as the base file or source file depending on the conversion direction)
3. Select the JP server Bundle file list (supports multiple files, can be dragged and dropped or browsed to select)
   - You can manually select multiple JP server Bundle files
   - If you have configured the game root directory in the settings and enabled "Auto Search", the matching JP files will be automatically found after selecting the Global server file
4. Click the "Convert" button
   - JP -> Global: The program will extract assets from the list of JP server Bundle files and merge them into the Global server version file
   - Global -> JP: The program will split the Global server format Bundle into the list of JP server Bundle files

## Extended Features

The extended features mentioned in this section are optional, and you can choose whether to enable them according to your needs.

The following extended features are independent third-party programs. Please comply with their licenses when downloading and using them. The BA Modding Toolkit repository does not contain or distribute any code or files of these programs, nor is it responsible for any issues that may arise during their use.

### Spine Converter

**[SpineSkeletonDataConverter](https://github.com/wang606/SpineSkeletonDataConverter)**

This program provides an interface to call the Skel conversion tool. Based on the SpineSkeletonDataConverter project, it can convert Spine 3 format `.skel` files used in some older Mods to the Spine 4 format supported by the current game version.

- Please download the corresponding program yourself. BAMT only provides the function to call the program for conversion and does not include the program itself.
- Configure the path of the `SpineSkeletonDataConverter.exe` program in the settings interface and check the "Enable Spine Conversion" option.

#### Reminder

- This is an experimental feature and cannot guarantee that all mods can be successfully upgraded. There may be inconsistencies before and after conversion.
- Even if `SpineSkeletonDataConverter.exe` is not configured, you can still use this program normally to update Mods that *use Spine files compatible with the current version (4.2.xx)*.
- If the Mod you want to update was made in 2025 or later, it already uses the Spine 4 format, so you can update it normally without configuring this option.

## Command Line Interface (CLI)

In addition to the graphical interface, this project provides a Command Line Interface (CLI) version `cli/`.

You can download the precompiled executable file `BAMT-CLI.exe` from the Release page or use the `uv run bamt-cli` command to run the source code.

### CLI Usage

All operations can be executed via the `bamt-cli` command. You can use `--help` to view all available commands and parameters.

```bash
# View all available commands
bamt-cli -h

# View detailed help and examples for a specific command
bamt-cli update -h
bamt-cli pack -h
bamt-cli crc -h

# View environment information
bamt-cli env
```

## Technical Details

### Tested Environments

The table below lists tested environment configurations for reference.

| Operating System | Python | UnityPy | Pillow | Status | Note   |
|:------------------- |:-------------- |:--------------- |:-------------- |:------ | :--- |
| Windows 10          | 3.12.4         | 1.23.0     | 12.0.0    | ✅   | Dev Env |
| Windows 10          | 3.12.4         | 1.23.0     | 10.4.0    | ✅   |  |
| Windows 10          | 3.13.7         | 1.23.0          | 11.3.0         | ✅     |  |
| Ubuntu 22.04 (WSL2) | 3.13.10        | 1.23.0          | 12.0.0         | ✅     |  |

## Developing

Please ensure that Python 3.12 or higher is installed.

```bash
git clone https://github.com/Agent-0808/BA-Modding-Toolkit.git
cd BA-Modding-Toolkit

# use uv to manage dependencies
python -m pip install uv
uv sync
uv run bamt
# or use legacy way to install dependencies
python -m pip install .
python -m ba_modding_toolkit
```

The author's programming skills are limited, welcome to provide suggestions or issues, and also welcome to contribute code to improve this project.

You can add `BA-Modding-Toolkit` code (mainly `core.py` and `utils.py`) to your project or modify the existing code to implement custom Mod creation and update functionality.

`cli/main.py` is a command-line interface (CLI) version of the main program, which you can refer to for calling processing functions.

### File Structure

```
BA-Modding-Toolkit/
│ 
│ # ============= Code =============
│ 
├── src/ba_modding_toolkit/
│ ├── __init__.py
│ ├── __main__.py    # Entry point
│ ├── core.py        # Core processing logic
│ ├── i18n.py        # Internationalization functionality
│ ├── utils.py       # Utility classes and helper functions
│ ├── cli/           # Command Line Interface (CLI) package
│ │ ├── __main__.py     # CLI Entry Point
│ │ ├── main.py         # CLI Main Program
│ │ ├── taps.py         # Command Line Argument Parsing
│ │ └── handlers.py     # Command Line Argument Handling
│ ├── gui/           # GUI package
│ │ ├── __init__.py
│ │ ├── main.py         # GUI program main entry point
│ │ ├── app.py          # Main application App class
│ │ ├── base_tab.py     # TabFrame base class
│ │ ├── components.py   # UI components, themes, logging
│ │ ├── dialogs.py      # Settings dialogs
│ │ ├── utils.py        # UI related utility functions
│ │ └── tabs/           # Feature tabs
│ │   ├── __init__.py
│ │   ├── mod_update_tab.py       # Mod Update tab
│ │   ├── crc_tool_tab.py         # CRC Fix Tool tab
│ │   ├── asset_packer_tab.py     # Asset Packer tab
│ │   ├── asset_extractor_tab.py  # Asset Extractor tab
│ │   └── jp_conversion_tab.py    # JP/GL Conversion tab
│ ├── assets/         # Project assets
│ └── locales/        # Language files
├── config.toml       # Local configuration file (automatically generated)
│ 
│ # ============= Misc. =============
│ 
├── requirements.txt # Python dependency list (for legacy installation)
├── pyproject.toml   # Python project configuration file
├── LICENSE          # Project license file
├── docs/            # Project documentation folder
│ └── help/              # Images in help documentation
├── README_zh-CN.md  # Project documentation (Chinese)
└── README.md        # Project documentation (this file)
```

## Acknowledgement

- [Deathemonic](https://github.com/Deathemonic): Patching CRC with [BA-CY](https://github.com/Deathemonic/BA-CY).
- [kalina](https://github.com/kalinaowo): Creating the prototype of the `CRCUtils` class.
- [afiseleo](https://github.com/fiseleo): Helping with the CLI version.
- [com55](https://github.com/com55): Assisting with Github workflow.

### Third-Party Libraries

This project uses the following excellent 3rd-party libraries:

- [UnityPy](https://github.com/K0lb3/UnityPy) (MIT License): Core library for parsing and manipulating Unity Bundle files
- [Pillow](https://python-pillow.github.io/) (MIT License): Image processing
- [tkinterdnd2](https://github.com/pmgagne/tkinterdnd2) (MIT License): Adds drag-and-drop functionality support for Tkinter
- [ttkbootstrap](https://github.com/israel-dryer/ttkbootstrap) (MIT License): Modern Tkinter theme library
- [toml](https://github.com/uiri/toml) (MIT License): Parse and dump TOML configuration file
- [SpineAtlas](https://github.com/Rin-Wood/SpineAtlas) (MIT License): Spine animation file atlas parser and editor
- [Tap](https://github.com/swansonk14/typed-argument-parser) (MIT License): Parsing command line arguments

### See Also

Some useful related repositories:

- [BA-characters-internal-id](https://github.com/Agent-0808/BA-characters-internal-id) ：Search for character names and internal file IDs
- [BA-AD](https://github.com/Deathemonic/BA-AD)：Download original game resources
- [SpineViewer](https://github.com/ww-rm/SpineViewer)：Preview Spine animation files

### Disclaimer

<sub>
BA Modding Toolkit is a personal project by Agent-0808 and is not affiliated with, endorsed by, or connected to NEXON Games Co., Ltd., NEXON Korea Corp., Yostar, Inc., or any of their subsidiaries. All game assets, characters, music, and related intellectual property are the trademarks or registered trademarks of their respective owners. They are used in this tool for educational and interoperability purposes only (fair use). Please respect the Terms of Service of the official game. Do not use this tool for cheating or malicious activities.
</sub>
