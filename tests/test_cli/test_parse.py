import pytest
from pathlib import Path

from ba_modding_toolkit.cli.taps import ParseTap
from ba_modding_toolkit.cli.handlers import handle_parse


class TestParseCommand:
    def test_parse_single(
        self,
    ):
        """测试解析单个文件名"""
        args = ParseTap().parse_args([
            "assets-_mx-spinecharacters-ch0808_spr-mxdependency-textures-2077-08-08_12345678.bundle",
        ])

        handle_parse(args)

    def test_parse_multiple(
        self,
    ):
        """测试解析多个文件名"""
        args = ParseTap().parse_args([
            "assets-_mx-spinecharacters-ch8080_spr-_mxdependency-2088-07-07_002_assets_all_7355608.bundle",
            "prologdepengroup-assets-_mx-characters-oooo_original-_mxprolog-2000-10-10_assets_all_111122223333.bundle",
            "ch0090_home_gl.bundle",
        ])

        handle_parse(args)

    def test_parse_with_bacii(
        self,
    ):
        """测试带 BACII 角色名解析（映射文件不存在时仅警告）"""
        args = ParseTap().parse_args([
            "assets-_mx-spinecharacters-ch0069_spr-mxdependency-textures-2077-08-08_12345678.bundle",
            "--bacii-path", "nonexistent.csv",
        ])

        handle_parse(args)
