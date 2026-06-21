"""
scripts/extract_version.py

从 pyproject.toml 提取版本号并生成 _version.py 文件
用于 GitHub Actions workflow 中，统一处理版本号提取逻辑。
"""

import os
import re
import tomllib


def main():
    # 读取 pyproject.toml
    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)
        version = data["project"]["version"]

    print(f"Detected version: {version}")

    # 生成 _version.py 供 Python 代码引用
    with open("src/ba_modding_toolkit/_version.py", "w", encoding="utf-8") as f:
        f.write(f'__version__ = "{version}"\n')

    # Nuitka 的 file-version 必须是纯数字格式 (如 1.2.3.4)
    # 提取开头的数字段（支持最多四段，遇到非数字/点就停）
    match = re.match(r'[vV]?(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?', version)
    if match:
        major, minor, patch, fourth = match.groups()
        major = major or '0'
        minor = minor or '0'
        patch = patch or '0'

        # 如果第四段已经存在（原版本号有四位数字），直接使用
        if fourth is not None:
            file_version = f"{major}.{minor}.{patch}.{fourth}"
        else:
            # 没有第四段，判断是否为预发布版
            if re.search(r'(alpha|beta|rc|dev|a|b|c)', version, re.I):
                file_version = f"{major}.{minor}.{patch}.8888"
            else:
                file_version = f"{major}.{minor}.{patch}.0"
    else:
        file_version = "0.0.0.0"
    print(f"File version for Nuitka: {file_version}")

    # 将版本号设置到 GitHub Action 的输出变量
    if 'GITHUB_OUTPUT' in os.environ:
        with open(os.environ['GITHUB_OUTPUT'], 'a') as fh:
            print(f"version={version}", file=fh)
            print(f"file_version={file_version}", file=fh)
    else:
        # 本地运行时输出到 stdout
        print(f"::set-output name=version::{version}")
        print(f"::set-output name=file_version::{file_version}")


if __name__ == "__main__":
    main()