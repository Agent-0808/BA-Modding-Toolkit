import pytest
from pathlib import Path

from ba_modding_toolkit.naming import get_category_prefix, parse_filename
from ba_modding_toolkit.searching import search_prefix, search_core

from conftest import (
    PACKER_DIR,
    has_mod_update_samples,
    has_legacy_format_samples,
    has_sample_skel,
    has_sample_image,
    has_sample_atlas,
    has_sample_bundle,
)

class TestParseFilename:
    def test_parse_filename_jp(self):
        filename = "assets-_mx-spinecharacters-ch0808_spr-mxdependency-textures-2077-08-08_12345678.bundle"
        parsed_filename = parse_filename(filename)
        
        assert parsed_filename.category == "spinecharacters"
        assert parsed_filename.core == "ch0808_spr"
        assert parsed_filename.res_type == "textures"
        assert parsed_filename.date == "2077-08-08"
        assert parsed_filename.crc == "12345678"
        assert parsed_filename.prefix == "assets-_mx-spinecharacters-ch0808_spr-mxdependency-"

    def test_parse_filename_global(self):
        filename = "assets-_mx-spinecharacters-ch8080_spr-_mxdependency-2088-07-07_002_assets_all_7355608.bundle"
        parsed = parse_filename(filename)
        
        assert parsed.category == "spinecharacters"
        assert parsed.core == "ch8080_spr"
        assert parsed.res_type == "002"
        assert parsed.date == "2088-07-07"
        assert parsed.crc == "7355608"
        assert parsed.prefix.startswith("assets-_mx-spinecharacters-ch8080_spr")

    def test_parse_filename_legacy(self):
        filename = "assets-_mx-spinecharacters-ch0088_spr-_mxdependency-1970-01-01_assets_all_072107210721.bundle"
        parsed = parse_filename(filename)
        
        assert parsed.category == "spinecharacters"
        assert parsed.core == "ch0088_spr"
        assert parsed.res_type is None
        assert parsed.date == "1970-01-01"
        assert parsed.crc == "072107210721"
        assert parsed.prefix.startswith("assets-_mx-spinecharacters-ch0088_spr")

    def test_parse_filename_lobby(self):
        filename = "assets-_mx-spinelobbies-ch0808_home-_mxdependency-2020-07-07_003_assets_all_888888888.bundle"
        parsed = parse_filename(filename)
        
        assert parsed.category == "spinelobbies"
        assert parsed.core == "ch0808_home"
        assert parsed.res_type == "003"
        assert parsed.date == "2020-07-07"
        assert parsed.crc == "888888888"
        assert parsed.prefix.startswith("assets-_mx-spinelobbies-ch0808_home")

    def test_parse_filename_model(self):
        filename = "assets-_mx-characters-ch3333-_mxdependency-meshes-2000-10-10_assets_all_45673210.bundle"
        parsed = parse_filename(filename)
        
        assert parsed.category == "characters"
        assert parsed.core == "ch3333"
        assert parsed.res_type == "meshes"
        assert parsed.date == "2000-10-10"
        assert parsed.crc == "45673210"
        assert parsed.prefix.startswith("assets-_mx-characters-ch3333")

    def test_parse_filename_with_mxload(self):
        filename = "uis-09_common-99_minigame-cardgame-_mxload-2088-07-07_assets_all_87654321.bundle"
        parsed = parse_filename(filename)
        
        assert "cardgame" in parsed.core
        assert parsed.res_type is None
        assert parsed.date == "2088-07-07"
        assert parsed.crc == "87654321"
        assert parsed.prefix.startswith("uis-09_common-99_minigame-cardgame")

    def test_parse_filename_no_type(self):
        filename = "assets-_mx-category-corename-2024-01-01_11111111.bundle"
        parsed = parse_filename(filename)
        
        assert parsed.category == "category"
        assert parsed.core == "corename"
        assert parsed.res_type is None
        assert parsed.date == "2024-01-01"
        assert parsed.crc == "11111111"
        assert parsed.prefix.startswith("assets-_mx-category-corename")

    def test_preload_filename_model(self):
        filename = "prologdepengroup-assets-_mx-characters-oooo_original-_mxprolog-2000-10-10_assets_all_111122223333.bundle"
        parsed = parse_filename(filename)
        
        assert parsed.category == "characters"
        assert parsed.core == "oooo_original"
        assert parsed.res_type is None
        assert parsed.date == "2000-10-10"
        assert parsed.crc == "111122223333"
        assert parsed.prefix.startswith("prologdepengroup-assets-_mx-characters-oooo_original")
    
    def test_preload_filename_spinechar(self):
        filename = "prologdepengroup-assets-_mx-spinecharacters-uouououo_spr-_mxprolog-2222-11-11_assets_all_7355608.bundle"
        parsed = parse_filename(filename)
        
        assert parsed.category == "spinecharacters"
        assert parsed.core == "uouououo_spr"
        assert parsed.res_type is None
        assert parsed.date == "2222-11-11"
        assert parsed.crc == "7355608"
        assert parsed.prefix.startswith("prologdepengroup-assets-_mx-spinecharacters-uouououo_spr")

class TestGetCategoryPrefix:
    """测试根据 core 后缀返回搜索前缀"""

    def test_home_suffix(self):
        """_home 后缀应返回 spinelobbies 前缀"""
        result = get_category_prefix("ch0999_home")
        assert result == "assets-_mx-spinelobbies-"

    def test_spr_suffix(self):
        """_spr 后缀应返回 spinecharacters 前缀"""
        result = get_category_prefix("ch0808_spr")
        assert result == "assets-_mx-spinecharacters-"

    def test_default_no_suffix(self):
        """无匹配后缀时返回默认前缀"""
        result = get_category_prefix("ch8888")
        assert result == "assets-_mx-characters-"

    def test_case_insensitive(self):
        """大小写不敏感"""
        result = get_category_prefix("CH0555_HOME")
        assert result == "assets-_mx-spinelobbies-"

        result = get_category_prefix("Ch0808_Spr")
        assert result == "assets-_mx-spinecharacters-"


class TestSearchPrefix:
    """测试前缀搜索功能"""

    def test_search_bundle_by_prefix(self, tmp_path: Path):
        """根据 bundle 文件名的 prefix 搜索其他 bundle 文件"""
        search_dir = tmp_path / "Windows"
        search_dir.mkdir()

        target1 = search_dir / "assets-_mx-spinelobbies-ch0721_home-mxdependency-2025-07-10_003_assets_all_12345.bundle"
        target2 = search_dir / "assets-_mx-spinelobbies-ch0721_home-mxdependency-2025-07-11_002_assets_all_67890.bundle"
        other1 = search_dir / "assets-_mx-spinecharacters-ch0808_spr-mxdependency-2025-07-10_002_assets_all_11111.bundle"

        for f in [target1, target2, other1]:
            f.write_bytes(b"test data")

        source = tmp_path / "assets-_mx-spinelobbies-ch0721_home-mxdependency-2024-01-01_textassets_assets_all_99999.bundle"
        source.write_bytes(b"old bundle data")

        candidates, err = search_prefix(source, [search_dir])
        assert err == ""
        assert len(candidates) == 2
        assert target1 in candidates
        assert target2 in candidates
        assert other1 not in candidates

    def test_search_not_found(self, tmp_path: Path):
        """无匹配文件时返回空列表"""
        search_dir = tmp_path / "Windows"
        search_dir.mkdir()

        source = tmp_path / "assets-_mx-spinelobbies-ch0721_home-mxdependency-2024-01-01_textassets_assets_all_99999.bundle"
        source.write_bytes(b"old bundle data")

        candidates, err = search_prefix(source, [search_dir])
        assert candidates == []
        assert err != ""

    def test_search_invalid_filename(self, tmp_path: Path):
        """无法解析 prefix 的文件名返回空"""
        search_dir = tmp_path / "Windows"
        search_dir.mkdir()

        source = tmp_path / "random_file.bundle"
        source.write_bytes(b"data")

        candidates, err = search_prefix(source, [search_dir])
        assert candidates == []
        assert err != ""

    @pytest.mark.skipif(
        not has_mod_update_samples(),
        reason="old_mod.bundle AND new_original.bundle ARE REQUIRED"
    )
    def test_search_mod_update_real_files(
        self,
        old_mod_bundle_path: Path,
        new_original_bundle_path: Path,
    ):
        """使用真实测试文件测试 mod update 搜索"""
        # 从旧 bundle 搜索新 bundle（使用 new 目录作为搜索目录）
        candidates, err = search_prefix(old_mod_bundle_path, [new_original_bundle_path.parent])

        assert err == ""
        assert len(candidates) >= 1
        # 新文件应该在结果中
        assert new_original_bundle_path in candidates


class TestSearchCore:
    """测试 core 搜索功能"""

    def test_search_by_core(self, tmp_path: Path):
        """根据 core 搜索 bundle 文件"""
        search_dir = tmp_path / "Windows"
        search_dir.mkdir()

        target1 = search_dir / "assets-_mx-spinelobbies-ch1437_home-mxdependency-2025-07-10_002_assets_all_12345.bundle"
        target2 = search_dir / "assets-_mx-spinelobbies-ch1437_home-mxload-2025-07-11_003_assets_all_67890.bundle"
        other1 = search_dir / "assets-_mx-spinelobbies-ch9999_home-mxdependency-2025-07-10_002_assets_all_11111.bundle"
        other2 = search_dir / "assets-_mx-spinelobbies-ch0888_spr-mxdependency-2025-07-10_002_assets_all_22222.bundle"

        for f in [target1, target2, other1, other2]:
            f.write_bytes(b"test data")

        source = tmp_path / "CH1437_home.skel"
        source.write_bytes(b"skel data")

        candidates, err = search_core(source, [search_dir])
        assert err == ""
        assert len(candidates) == 2
        assert target1 in candidates
        assert target2 in candidates
        assert other1 not in candidates
        assert other2 not in candidates

    def test_search_skel_to_bundle(self, tmp_path: Path):
        """测试 .skel 源文件搜索 .bundle 目标文件"""
        search_dir = tmp_path / "Windows"
        search_dir.mkdir()

        target = search_dir / "assets-_mx-spinelobbies-ch1437_home-mxdependency-2025-07-10_002_assets_all_12345.bundle"
        target.write_bytes(b"test data")

        source = tmp_path / "CH1437_home.skel"
        source.write_bytes(b"skel data")

        candidates, err = search_core(source, [search_dir])
        assert err == ""
        assert len(candidates) == 1
        assert target in candidates

    def test_search_png_to_bundle(self, tmp_path: Path):
        """测试 .png 源文件搜索 .bundle 目标文件"""
        search_dir = tmp_path / "Windows"
        search_dir.mkdir()

        target = search_dir / "assets-_mx-spinecharacters-ch0808_spr-mxdependency-2025-07-10_002_assets_all_12345.bundle"
        target.write_bytes(b"test data")

        source = tmp_path / "ch0808_spr.png"
        source.write_bytes(b"png data")

        candidates, err = search_core(source, [search_dir])
        assert err == ""
        assert len(candidates) == 1
        assert target in candidates

    def test_search_only_bundle_files(self, tmp_path: Path):
        """只搜索 .bundle 文件，忽略其他后缀"""
        search_dir = tmp_path / "Windows"
        search_dir.mkdir()

        bundle_file = search_dir / "assets-_mx-spinelobbies-ch1437_home-mxdependency-2025-07-10_002_assets_all_12345.bundle"
        txt_file = search_dir / "assets-_mx-spinelobbies-ch1437_home-mxdependency-2025-07-10_002_assets_all_12345.txt"
        meta_file = search_dir / "assets-_mx-spinelobbies-ch1437_home-mxdependency-2025-07-10_002_assets_all_12345.meta"

        for f in [bundle_file, txt_file, meta_file]:
            f.write_bytes(b"test data")

        source = tmp_path / "CH1437_home.skel"
        source.write_bytes(b"skel data")

        candidates, err = search_core(source, [search_dir])
        assert err == ""
        assert len(candidates) == 1
        assert bundle_file in candidates
        assert txt_file not in candidates
        assert meta_file not in candidates

    def test_search_case_insensitive(self, tmp_path: Path):
        """大小写不敏感匹配"""
        search_dir = tmp_path / "Windows"
        search_dir.mkdir()
        target = search_dir / "assets-_mx-spinelobbies-CH1437_HOME-mxdependency-2025-07-10_002_assets_all_12345.bundle"
        target.write_bytes(b"test data")

        source = tmp_path / "ch1437_home.skel"
        source.write_bytes(b"skel data")

        candidates, err = search_core(source, [search_dir])
        assert err == ""
        assert len(candidates) == 1
        assert target in candidates

    def test_search_not_found(self, tmp_path: Path):
        """无匹配文件时返回空列表"""
        search_dir = tmp_path / "Windows"
        search_dir.mkdir()

        source = tmp_path / "CH1437_home.skel"
        source.write_bytes(b"skel data")

        candidates, err = search_core(source, [search_dir])
        assert candidates == []
        assert err != ""

    def test_search_invalid_filename(self, tmp_path: Path):
        """无法解析的文件名返回空"""
        search_dir = tmp_path / "Windows"
        search_dir.mkdir()

        source = tmp_path / "random_file.skel"
        source.write_bytes(b"skel data")

        candidates, err = search_core(source, [search_dir])
        assert candidates == []
        assert err != ""

    @pytest.mark.skipif(
        not has_mod_update_samples(),
        reason="old_mod.bundle AND new_original.bundle ARE REQUIRED"
    )
    def test_search_mod_update_by_core(
        self,
        old_mod_bundle_path: Path,
        new_original_bundle_path: Path,
    ):
        """使用真实测试文件测试 core 搜索（mod update 场景）"""
        # 从旧 bundle 搜索新 bundle
        candidates, err = search_core(old_mod_bundle_path, [new_original_bundle_path.parent])

        assert err == ""
        assert len(candidates) >= 1
        assert new_original_bundle_path in candidates

    @pytest.mark.skipif(
        not has_legacy_format_samples(),
        reason="legacy AND modern bundles ARE REQUIRED"
    )
    def test_search_legacy_to_modern(
        self,
        legacy_bundle_path: Path,
        modern_bundles_path: list[Path],
    ):
        """使用真实测试文件测试 legacy 格式搜索 modern bundle"""
        if not modern_bundles_path:
            pytest.skip("No modern bundles found")

        # 从 legacy bundle 搜索 modern bundle
        modern_dir = modern_bundles_path[0].parent
        candidates, err = search_core(legacy_bundle_path, [modern_dir])

        assert err == ""
        assert len(candidates) >= 1
        # 至少有一个 modern bundle 应该匹配
        assert any(c in modern_bundles_path for c in candidates)

    class TestWithPackerSamples:
        """使用 packer 目录真实文件的搜索测试"""

        @pytest.mark.skipif(
            not (has_sample_skel() and has_sample_bundle()),
            reason=".skel AND .bundle files ARE REQUIRED"
        )
        def test_search_skel_to_bundle_real(
            self,
            sample_skel_path: Path,
            sample_bundle_path: Path,
        ):
            """使用真实的 .skel 文件搜索 bundle"""
            candidates, err = search_core(sample_skel_path, [PACKER_DIR])

            assert err == ""
            assert len(candidates) >= 1
            assert sample_bundle_path in candidates

        @pytest.mark.skipif(
            not (has_sample_image() and has_sample_bundle()),
            reason=".png AND .bundle files ARE REQUIRED"
        )
        def test_search_png_to_bundle_real(
            self,
            sample_image_path: Path,
            sample_bundle_path: Path,
        ):
            """使用真实的 .png 文件搜索 bundle"""
            candidates, err = search_core(sample_image_path, [PACKER_DIR])

            assert err == ""
            assert len(candidates) >= 1
            assert sample_bundle_path in candidates

        @pytest.mark.skipif(
            not (has_sample_atlas() and has_sample_bundle()),
            reason=".atlas AND .bundle files ARE REQUIRED"
        )
        def test_search_atlas_to_bundle_real(
            self,
            sample_atlas_path: Path,
            sample_bundle_path: Path,
        ):
            """使用真实的 .atlas 文件搜索 bundle"""
            candidates, err = search_core(sample_atlas_path, [PACKER_DIR])

            assert err == ""
            assert len(candidates) >= 1
            assert sample_bundle_path in candidates


class TestParseAndSearchRoundtrip:
    """测试 parse_filename 和 search 的往返一致性"""

    def test_parse_then_search_by_core(self, tmp_path: Path):
        """解析 bundle 文件名得到 core，再用 core 搜索应能找回原文件"""
        search_dir = tmp_path / "Windows"
        search_dir.mkdir()

        # 创建测试 bundle 文件
        bundle_name = "assets-_mx-spinelobbies-np0721_home-mxdependency-2025-07-10_002_assets_all_99999.bundle"
        bundle_path = search_dir / bundle_name
        bundle_path.write_bytes(b"test data")

        # 1. 解析 bundle 文件名
        parsed = parse_filename(bundle_name)

        # 2. 验证解析结果
        assert parsed.core == "np0721_home"
        assert parsed.date == "2025-07-10"

        # 3. 用解析出的 core 重新搜索
        fake_asset = tmp_path / f"{parsed.core}.skel"
        fake_asset.write_bytes(b"fake skel")

        candidates, err = search_core(fake_asset, [search_dir])

        # 4. 应能找到原 bundle
        assert err == ""
        assert len(candidates) >= 1
        assert bundle_path in candidates

    def test_parse_then_search_different_extensions(self, tmp_path: Path):
        """同一 core 的不同资源文件应都能搜索到同一 bundle"""
        search_dir = tmp_path / "Windows"
        search_dir.mkdir()

        bundle_name = "assets-_mx-spinecharacters-ch1437_spr-mxdependency-2025-07-10_002_assets_all_12345.bundle"
        bundle_path = search_dir / bundle_name
        bundle_path.write_bytes(b"test data")

        parsed = parse_filename(bundle_name)
        assert parsed.core == "ch1437_spr"

        # 用不同扩展名搜索
        for ext in [".skel", ".png", ".atlas"]:
            asset_path = tmp_path / f"{parsed.core}{ext}"
            asset_path.write_bytes(b"test")

            candidates, err = search_core(asset_path, [search_dir])
            assert err == ""
            assert bundle_path in candidates

    def test_parse_preserves_core_for_search(self, tmp_path: Path):
        """解析出的 core 应足够用于搜索匹配"""
        search_dir = tmp_path / "Windows"
        search_dir.mkdir()

        # 创建多个版本的同 core bundle
        bundle_v1 = search_dir / "assets-_mx-spinelobbies-np8888_home-mxdependency-2025-01-01_001_assets_all_11111.bundle"
        bundle_v2 = search_dir / "assets-_mx-spinelobbies-np8888_home-mxdependency-2025-07-10_002_assets_all_22222.bundle"
        bundle_v3 = search_dir / "assets-_mx-spinelobbies-np8888_home-mxload-2025-07-11_003_assets_all_33333.bundle"

        for f in [bundle_v1, bundle_v2, bundle_v3]:
            f.write_bytes(b"test data")

        # 解析任一版本
        parsed = parse_filename(bundle_v2.name)
        core = parsed.core

        # 用 core 搜索
        asset = tmp_path / f"{core}.png"
        asset.write_bytes(b"test")

        candidates, err = search_core(asset, [search_dir])

        # 应找到所有版本
        assert err == ""
        assert len(candidates) == 3
        assert bundle_v1 in candidates
        assert bundle_v2 in candidates
        assert bundle_v3 in candidates

    @pytest.mark.skipif(
        not (has_sample_skel() and has_sample_bundle()),
        reason=".skel AND .bundle files ARE REQUIRED"
    )
    def test_roundtrip_with_real_bundle(
        self,
        sample_bundle_path: Path,
        sample_skel_path: Path,
    ):
        """使用真实 bundle 文件测试往返"""
        # 1. 解析真实 bundle 文件名
        parsed = parse_filename(sample_bundle_path.name)
        assert parsed.core is not None

        # 2. 使用已有的真实 .skel 文件搜索
        candidates, err = search_core(sample_skel_path, [PACKER_DIR])

        # 3. 应找到原 bundle
        assert err == ""
        assert sample_bundle_path in candidates