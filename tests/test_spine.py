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
        normalize_legacy_assets
    )
from conftest import has_sample_skel, has_sample_atlas, file_list


class TestNormalizeLegacySpineAssets:
    """测试 normalize_legacy_spine_assets 函数"""

    def test_normalize_no_rename_needed(self, tmp_path: Path):
        """测试不需要重命名的文件"""
        test_file = tmp_path / "CH0808_home.png"
        test_file.write_bytes(b"fake png data")

        result = normalize_legacy_assets(tmp_path)
        assert result.exists()

        files = list(result.glob("*.png"))
        assert len(files) == 1
        assert files[0].name == "CH0808_home.png"

    def test_normalize_rename_png_file(self, tmp_path: Path):
        """测试 PNG 文件重命名 (CH0808_home2 -> CH0808_home_2)"""
        test_file = tmp_path / "CH0808_home2.png"
        test_file.write_bytes(b"fake png data")

        result = normalize_legacy_assets(tmp_path)
        assert result.exists()

        files = list(result.glob("*.png"))
        assert len(files) == 1
        assert files[0].name == "CH0808_home_2.png"

    def test_normalize_rename_multiple_files(self, tmp_path: Path):
        """测试多个文件重命名"""
        (tmp_path / "CH0144.png").write_bytes(b"data1")
        (tmp_path / "CH0808_home2.png").write_bytes(b"data2")
        (tmp_path / "CH9999_abc3.png").write_bytes(b"data3")

        result = normalize_legacy_assets(tmp_path)
        assert result.exists()

        files = sorted([f.name for f in file_list(result)])
        assert "CH014_4.png" in files
        assert "CH0808_home_2.png" in files
        assert "CH9999_abc_3.png" in files

    def test_normalize_updates_atlas_references(self, tmp_path: Path):
        """测试 atlas 文件中的引用更新"""
        png_file = tmp_path / "CH0808_home2.png"
        png_file.write_bytes(b"fake png data")

        atlas_file = tmp_path / "test.atlas"
        atlas_content = """
CH0808_home2.png
size: 512, 512
format: RGBA8888
filter: Linear, Linear
repeat: none
animation
  rotate: false
  xy: 0, 0
  size: 100, 100
"""
        atlas_file.write_text(atlas_content, encoding="utf-8")

        result = normalize_legacy_assets(tmp_path)
        assert result.exists()

        result_atlas = result / "test.atlas"
        assert result_atlas.exists()

        result_content = result_atlas.read_text(encoding="utf-8")
        assert "CH0808_home_2.png" in result_content
        assert "CH0808_home2.png" not in result_content

        shutil.rmtree(result, ignore_errors=True)

    def test_normalize_preserves_original_files(self, tmp_path: Path):
        """测试原始文件不被修改"""
        original_file = tmp_path / "CH0808_home2.png"
        original_file.write_bytes(b"original data")

        result = normalize_legacy_assets(tmp_path)
        assert result.exists()

        assert original_file.exists()
        assert original_file.read_bytes() == b"original data"
        assert original_file.name == "CH0808_home2.png"


    def test_normalize_with_skel_and_atlas(self, tmp_path: Path):
        """测试同时处理 skel 和 atlas 文件"""
        (tmp_path / "CH0808_home2.png").write_bytes(b"png data")
        (tmp_path / "CH0808_home2.skel").write_bytes(b"skel data")
        (tmp_path / "CH0808_home2.atlas").write_text(
            "CH0808_home2.png\nsize: 256, 256", encoding="utf-8"
        )

        result = normalize_legacy_assets(tmp_path)
        assert result.exists()

        assert (result / "CH0808_home_2.png").exists()
        assert (result / "CH0808_home2.skel").exists()
        assert (result / "CH0808_home2.atlas").exists()

        atlas_content = (result / "CH0808_home2.atlas").read_text(encoding="utf-8")
        assert "CH0808_home_2.png" in atlas_content

        shutil.rmtree(result, ignore_errors=True)


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