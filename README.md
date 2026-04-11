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
- **JP/GL Conversion**: Convert between JP server format and Legacy Global server format
  - Convert between a single file and multiple files
  - Batch convert legacy Global server format to new format

Check the [Usage](https://github.com/Agent-0808/BA-Modding-Toolkit/wiki/Usage) Page for detailed instructions.

![How to update a mod with BAMT GUI](docs/help/gui-help-mod-update-en.png)

## Extended Features

The extended features mentioned in this section are optional, and you can choose whether to enable them according to your needs.

The following extended features are independent third-party programs. Please comply with their licenses when downloading and using them. The BA Modding Toolkit repository does not contain or distribute any code or files of these programs, nor is it responsible for any issues that may arise during their use.

### Spine Converter

**[SpineSkeletonDataConverter](https://github.com/wang606/SpineSkeletonDataConverter)**

This program provides an interface to call the Skel conversion tool. Based on the SpineSkeletonDataConverter project, it can convert Spine 3 format `.skel` files used in some older Mods to the Spine 4 format supported by the current game version. Additionally, it can convert Spine 4 format files to Spine 3 format in the "Asset Extractor" feature.

- Please download the corresponding program yourself. BAMT only provides the function to call the program for conversion and does not include the program itself.
- Configure the path of the `SpineSkeletonDataConverter.exe` program in the settings interface and check the "Enable Spine Conversion" option.

#### Reminder

- This is an experimental feature and cannot guarantee that all mods can be successfully upgraded. There may be inconsistencies before and after conversion.
- Even if `SpineSkeletonDataConverter.exe` is not configured, you can still use this program normally to update Mods that *use Spine files compatible with the current version (4.2.xx)*.
- If the Mod you want to update was made in 2025 or later, it already uses the Spine 4 format, so you can update it normally without configuring this option.

## Command Line Interface (CLI)

In addition to the graphical interface, this project provides a Command Line Interface (CLI) version `cli/`.

You can download the precompiled executable file `BAMT-CLI.exe` from the [Releases](https://github.com/Agent-0808/BA-Modding-Toolkit/releases) page or use the `uv run bamt-cli` command to run the source code.

### CLI Usage

All operations can be executed via the `bamt-cli` command. You can use `--help` to view all available commands and parameters.

```bash
# View all available commands
bamt-cli -h

# View detailed help and examples for a specific command
bamt-cli update -h
bamt-cli batch-update -h
bamt-cli merge -h
bamt-cli split -h
bamt-cli batch-legacy -h
bamt-cli pack -h
bamt-cli extract -h
bamt-cli crc -h

# View environment information
bamt-cli env
```

> Note: Due to the technical limitation of the `Tap` library, the compiled binary file cannot display parameter variable annotations. When running the source code, the parameter variable annotations will be displayed in the help information.

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
├── tests/            # Pytest test cases folder
│ ├── assets/         # Test assets
│ └── test_*.py       # Test cases
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

Thank you to all contributors for their valuable contributions.

Special thanks to:

- [Deathemonic](https://github.com/Deathemonic): Patching CRC with [BA-CY](https://github.com/Deathemonic/BA-CY).
- [kalina](https://github.com/kalinaowo): Creating the prototype of the `CRCUtils` class.

### Third-Party Libraries

This project uses the following excellent 3rd-party libraries:

- [UnityPy](https://github.com/K0lb3/UnityPy) (MIT License): Core library for parsing and manipulating Unity Bundle files
- [Pillow](https://python-pillow.github.io/) (MIT License): Image processing
- [tkinterdnd2](https://github.com/pmgagne/tkinterdnd2) (MIT License): Adds drag-and-drop functionality support for Tkinter
- [ttkbootstrap](https://github.com/israel-dryer/ttkbootstrap) (MIT License): Modern Tkinter theme library
- [toml](https://github.com/uiri/toml) (MIT License): Parse and dump TOML configuration file
- [SpineAtlas](https://github.com/Rin-Wood/SpineAtlas) (MIT License): Spine animation file atlas parser and editor
- [Tap](https://github.com/swansonk14/typed-argument-parser) (MIT License): Parsing command line arguments
- [pytest](https://pytest.org/en/stable/) (MIT License): Test framework

### See Also

Some useful related repositories:

- [BA-characters-internal-id](https://github.com/Agent-0808/BA-characters-internal-id) ：Search for character names and internal file IDs
- [BA-AD](https://github.com/Deathemonic/BA-AD)：Download original game resources
- [SpineViewer](https://github.com/ww-rm/SpineViewer)：Preview Spine animation files

### Disclaimer

<sub>
BA Modding Toolkit is a personal project and is not affiliated with, endorsed by, or connected to NEXON Games Co., Ltd., NEXON Korea Corp., Yostar, Inc., or any of their subsidiaries. All game assets, characters, music, and related intellectual property are the trademarks or registered trademarks of their respective owners. They are used in this tool for educational and interoperability purposes only (fair use). Please respect the Terms of Service of the official game. Do not use this tool for cheating or malicious activities.
</sub>
