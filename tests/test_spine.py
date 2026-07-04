"""
Spine 工具函数测试
"""

import pytest
from pathlib import Path
import shutil
import SpineAtlas

from ba_modding_toolkit.spine import (
        get_skel_version,
        atlas_downgrade,
        unpack_atlas,
        _build_rename_mapping,
        check_legacy_rename_needed,
        normalize_legacy_assets
    )
from ba_modding_toolkit.bundle import Bundle
from ba_modding_toolkit.models import NameTypeKey, AssetType
from conftest import has_sample_skel, has_sample_atlas, has_spine_legacy_samples, file_list


# Bundle 中 Texture2D 的名称集合（不含后缀），模拟真实 bundle 场景
MOCK_BUNDLE_PNG_NAMES = {"CH0808_home", "CH0808_home_2", "CH0808_home_3"}


class TestCheckLegacyRenameNeeded:
    """测试 check_legacy_rename_needed 函数"""

    def test_no_png_files(self, tmp_path: Path):
        """没有 PNG 文件时不需要重命名"""
        assert check_legacy_rename_needed(tmp_path, MOCK_BUNDLE_PNG_NAMES) is False

    def test_disk_matches_bundle(self, tmp_path: Path):
        """磁盘文件名与 Bundle 一致时不需要重命名"""
        (tmp_path / "CH0808_home.png").write_bytes(b"data")
        assert check_legacy_rename_needed(tmp_path, MOCK_BUNDLE_PNG_NAMES) is False

    def test_disk_mismatch_with_bundle(self, tmp_path: Path):
        """磁盘 CH0808_home2.png 与 Bundle CH0808_home_2 不匹配 → 需要重命名"""
        (tmp_path / "CH0808_home2.png").write_bytes(b"data")
        assert check_legacy_rename_needed(tmp_path, MOCK_BUNDLE_PNG_NAMES) is True

    def test_CH08082_renamed_to_CH0808_2(self, tmp_path: Path):
        """CH08082.png（旧版导出）应重命名为 CH0808_2 匹配 Bundle"""
        bundle_names = {"CH0808", "CH0808_2"}
        (tmp_path / "CH0808.png").write_bytes(b"data1")
        (tmp_path / "CH08082.png").write_bytes(b"data2")
        assert check_legacy_rename_needed(tmp_path, bundle_names) is True

    def test_multiple_mismatches(self, tmp_path: Path):
        """多个文件需要重命名"""
        (tmp_path / "CH0808_home2.png").write_bytes(b"data1")
        (tmp_path / "CH0808_home3.png").write_bytes(b"data2")
        assert check_legacy_rename_needed(tmp_path, MOCK_BUNDLE_PNG_NAMES) is True

    def test_no_matching_bundle_entry(self, tmp_path: Path):
        """磁盘文件名无法匹配任何 Bundle 条目时不重命名"""
        (tmp_path / "random_file2.png").write_bytes(b"data")
        assert check_legacy_rename_needed(tmp_path, MOCK_BUNDLE_PNG_NAMES) is False

    def test_empty_bundle_names(self, tmp_path: Path):
        """Bundle 名称集合为空时不重命名"""
        (tmp_path / "CH0808_home2.png").write_bytes(b"data")
        assert check_legacy_rename_needed(tmp_path, set()) is False


class TestNormalizeLegacySpineAssets:
    """测试 normalize_legacy_assets 函数"""

    def test_disk_matches_bundle_no_rename(self, tmp_path: Path):
        """磁盘文件名与 Bundle 一致时不重命名"""
        (tmp_path / "CH0808_home.png").write_bytes(b"data")
        result = normalize_legacy_assets(tmp_path, MOCK_BUNDLE_PNG_NAMES)
        assert (result / "CH0808_home.png").exists()

    def test_rename_to_match_bundle(self, tmp_path: Path):
        """磁盘文件 CH0808_home2.png 重命名为 Bundle 中的 CH0808_home_2"""
        (tmp_path / "CH0808_home2.png").write_bytes(b"png data")
        result = normalize_legacy_assets(tmp_path, MOCK_BUNDLE_PNG_NAMES)
        assert (result / "CH0808_home_2.png").exists()
        assert not (result / "CH0808_home2.png").exists()
        assert (result / "CH0808_home_2.png").read_bytes() == b"png data"

    def test_CH0808_not_renamed(self, tmp_path: Path):
        """CH0808.png 在 Bundle 中也是 CH0808 时不应被误改"""
        bundle_names = {"CH0808"}
        (tmp_path / "CH0808.png").write_bytes(b"data")
        result = normalize_legacy_assets(tmp_path, bundle_names)
        assert (result / "CH0808.png").exists()
        assert not (result / "CH080_8.png").exists()

    def test_CH08082_renamed_to_CH0808_2(self, tmp_path: Path):
        """CH08082.png（旧版导出）应重命名为 CH0808_2"""
        bundle_names = {"CH0808", "CH0808_2"}
        (tmp_path / "CH0808.png").write_bytes(b"data1")
        (tmp_path / "CH08082.png").write_bytes(b"data2")
        result = normalize_legacy_assets(tmp_path, bundle_names)
        assert (result / "CH0808.png").exists()
        assert (result / "CH0808_2.png").exists()
        assert not (result / "CH08082.png").exists()
        assert (result / "CH0808_2.png").read_bytes() == b"data2"

    def test_atlas_references_updated(self, tmp_path: Path):
        """Atlas 中旧版 PNG 引用应被更新为新版名称"""
        (tmp_path / "CH0808_home2.png").write_bytes(b"png data")
        # 旧版 atlas 引用旧版 PNG 名称
        (tmp_path / "test.atlas").write_text(
            "CH0808_home2.png\nsize: 512, 512\nformat: RGBA8888\n"
            "filter: Linear, Linear\nrepeat: none\n"
            "frame1\n  rotate: false\n  xy: 0, 0\n  size: 100, 100\n"
            "  orig: 100, 100\n  offset: 0, 0\n  index: -1\n",
            encoding="utf-8"
        )
        result = normalize_legacy_assets(tmp_path, MOCK_BUNDLE_PNG_NAMES)
        result_atlas_content = (result / "test.atlas").read_text(encoding="utf-8")
        assert "CH0808_home_2.png" in result_atlas_content
        assert "CH0808_home2.png" not in result_atlas_content

    def test_atlas_already_correct_not_modified(self, tmp_path: Path):
        """Atlas 引用已经是新版名称时不被修改"""
        (tmp_path / "CH0808_home.png").write_bytes(b"data")
        atlas_content = (
            "CH0808_home.png\nsize: 512, 512\nformat: RGBA8888\n"
            "filter: Linear, Linear\nrepeat: none\n"
            "frame1\n  rotate: false\n  xy: 0, 0\n  size: 100, 100\n"
            "  orig: 100, 100\n  offset: 0, 0\n  index: -1\n"
        )
        (tmp_path / "test.atlas").write_text(atlas_content, encoding="utf-8")
        result = normalize_legacy_assets(tmp_path, MOCK_BUNDLE_PNG_NAMES)
        result_atlas_content = (result / "test.atlas").read_text(encoding="utf-8")
        assert result_atlas_content == atlas_content

    def test_preserves_original_files(self, tmp_path: Path):
        """原始文件不被修改"""
        original = tmp_path / "CH0808_home2.png"
        original.write_bytes(b"original data")
        result = normalize_legacy_assets(tmp_path, MOCK_BUNDLE_PNG_NAMES)
        assert original.exists()
        assert original.read_bytes() == b"original data"
        assert original.name == "CH0808_home2.png"

    def test_non_png_files_preserved(self, tmp_path: Path):
        """skel 等非 PNG 文件原样保留"""
        (tmp_path / "CH0808_home2.png").write_bytes(b"png data")
        (tmp_path / "CH0808_home2.skel").write_bytes(b"skel data")
        result = normalize_legacy_assets(tmp_path, MOCK_BUNDLE_PNG_NAMES)
        assert (result / "CH0808_home_2.png").exists()
        assert (result / "CH0808_home2.skel").exists()
        assert (result / "CH0808_home2.skel").read_bytes() == b"skel data"

    def test_multiple_renames(self, tmp_path: Path):
        """多个文件同时重命名"""
        (tmp_path / "CH0808_home.png").write_bytes(b"data1")
        (tmp_path / "CH0808_home2.png").write_bytes(b"data2")
        (tmp_path / "CH0808_home3.png").write_bytes(b"data3")
        result = normalize_legacy_assets(tmp_path, MOCK_BUNDLE_PNG_NAMES)
        assert (result / "CH0808_home.png").exists()
        assert (result / "CH0808_home_2.png").exists()
        assert (result / "CH0808_home_3.png").exists()
        assert not (result / "CH0808_home2.png").exists()
        assert not (result / "CH0808_home3.png").exists()


class TestGetSkelVersion:
    """测试 get_skel_version 函数"""

    def test_get_version_from_bytes_with_version(self):
        """测试从字节数据中提取版本号"""
        skel_data = b"spine\x00\x00\x00\x004.2.33\x00rest of data"
        version = get_skel_version(skel_data)
        assert version == "4.2.33"

    def test_get_version_from_bytes_spine_3(self):
        """测试提取 Spine 3.x 版本号"""
        skel_data = b"spine\x00\x00\x00\x003.8.75\x00rest of data"
        version = get_skel_version(skel_data)
        assert version == "3.8.75"

    def test_get_version_no_version_found(self):
        """测试未找到版本号的情况"""
        data = b"no version string here\x00\x00\x00"
        version = get_skel_version(data)
        assert version is None

    def test_get_version_empty_data(self):
        """测试空数据"""
        version = get_skel_version(b"")
        assert version is None

    @pytest.mark.skipif(
        not has_sample_skel(),
        reason="sample.skel IS REQUIRED"
    )
    def test_get_version_from_file(self, sample_skel_path: Path):
        """测试从文件中提取版本号"""
        version = get_skel_version(sample_skel_path)
        assert version is not None
        assert "." in version
        assert len(version.split(".")) == 3


@pytest.mark.skipif(
    not has_sample_atlas(),
    reason="sample.atlas IS REQUIRED"
)
class TestAtlasOperations:
    """测试 Atlas 相关操作"""

    def test_process_atlas_downgrade(self, sample_atlas_path: Path, tmp_path: Path):
        """测试 atlas 降级处理"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        shutil.copy(sample_atlas_path, output_dir / sample_atlas_path.name)

        atlas_downgrade(
            sample_atlas_path, output_dir
        )

        files = list(output_dir.glob("*.atlas"))
        assert len(files) == 1
        output_atlas = SpineAtlas.ReadAtlasFile(files[0])
        assert output_atlas.version == False # Spine 3

    def test_unpack_atlas_frames(self, sample_atlas_path: Path, tmp_path: Path):
        """测试解包 atlas 帧"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = unpack_atlas(
            sample_atlas_path, output_dir
        )
        assert result

        images_dir = output_dir / "images"
        assert images_dir.exists()
        assert images_dir.is_dir()
        files = file_list(images_dir)
        assert len(files) > 1
        assert all(file.suffix == ".png" for file in files)


@pytest.mark.skipif(
    not has_spine_legacy_samples(),
    reason="spine/old_assets/ and spine/new_bundle/ ARE REQUIRED"
)
class TestLegacyRenameWithRealData:
    """使用真实 Spine 资产数据测试旧版文件名修正

    模拟真实场景：旧版磁盘文件 + 新版 Bundle → 需要重命名磁盘文件以匹配 Bundle
    """

    @pytest.fixture
    def bundle_png_names(self, spine_new_bundle_dir: Path) -> set[str]:
        """从真实 Bundle 中提取 Texture2D 名称"""
        names: set[str] = set()
        for bundle_file in spine_new_bundle_dir.glob("*.bundle"):
            bundle = Bundle.load(bundle_file)
            if bundle:
                for key in bundle.get_asset_keys(asset_types={AssetType.Texture2D}):
                    if isinstance(key, NameTypeKey) and key.name:
                        names.add(key.name)
        return names

    def test_old_assets_need_rename(self, spine_old_assets_dir: Path, bundle_png_names: set[str]):
        """旧版磁盘文件与 Bundle 名称不匹配 → 需要重命名"""
        assert bundle_png_names, "Bundle 中未找到 Texture2D 资产"
        assert check_legacy_rename_needed(spine_old_assets_dir, bundle_png_names) is True

    def test_rename_old_png_to_match_bundle(self, spine_old_assets_dir: Path, bundle_png_names: set[str]):
        """旧版 PNG 被重命名为 Bundle 中的名称"""
        assert bundle_png_names, "Bundle 中未找到 Texture2D 资产"

        result = normalize_legacy_assets(spine_old_assets_dir, bundle_png_names)

        # Bundle 中应有带下划线的名称
        for name in bundle_png_names:
            assert (result / f"{name}.png").exists(), f"期望 {name}.png 存在"

        # 旧版名称不应存在（如果已被重命名）
        old_stems = {f.stem for f in spine_old_assets_dir.iterdir() if f.suffix.lower() == '.png'}
        mapping = _build_rename_mapping(bundle_png_names, old_stems)
        for old_stem in mapping:
            assert not (result / f"{old_stem}.png").exists(), f"旧版 {old_stem}.png 不应存在"

    def test_renamed_png_data_matches_original(self, spine_old_assets_dir: Path, bundle_png_names: set[str]):
        """重命名后的 PNG 数据应与原始文件一致"""
        assert bundle_png_names, "Bundle 中未找到 Texture2D 资产"

        result = normalize_legacy_assets(spine_old_assets_dir, bundle_png_names)

        old_stems = {f.stem for f in spine_old_assets_dir.iterdir() if f.suffix.lower() == '.png'}
        mapping = _build_rename_mapping(bundle_png_names, old_stems)

        for old_stem, new_stem in mapping.items():
            old_data = (spine_old_assets_dir / f"{old_stem}.png").read_bytes()
            new_data = (result / f"{new_stem}.png").read_bytes()
            assert old_data == new_data, f"{old_stem}.png 数据不匹配 {new_stem}.png"

    def test_atlas_references_updated(self, spine_old_assets_dir: Path, bundle_png_names: set[str]):
        """旧版 atlas 中的旧版 PNG 引用应被更新为新版名称"""
        assert bundle_png_names, "Bundle 中未找到 Texture2D 资产"

        result = normalize_legacy_assets(spine_old_assets_dir, bundle_png_names)

        old_stems = {f.stem for f in spine_old_assets_dir.iterdir() if f.suffix.lower() == '.png'}
        mapping = _build_rename_mapping(bundle_png_names, old_stems)

        for atlas_file in result.glob('*.atlas'):
            content = atlas_file.read_text(encoding='utf-8')
            for old_stem in mapping:
                assert f"{old_stem}.png" not in content, f"Atlas 中仍包含旧版引用 {old_stem}.png"

    def test_skel_not_modified(self, spine_old_assets_dir: Path, bundle_png_names: set[str]):
        """skel 文件不受影响"""
        assert bundle_png_names, "Bundle 中未找到 Texture2D 资产"

        result = normalize_legacy_assets(spine_old_assets_dir, bundle_png_names)

        for skel_file in spine_old_assets_dir.glob('*.skel'):
            assert (result / skel_file.name).exists()
            assert (result / skel_file.name).read_bytes() == skel_file.read_bytes()
