"""SkelConverter 单元级测试：版本升级 / 降级 / roundtrip。

外部工具缺失时自动跳过；素材版本不固定，setup 时通过版本自举构造基准副本
（不动原始 asset），转换断言采用双层策略：
  1. subprocess 层：run() 返回 True
  2. 运行时层：get_skel_version 版本号正确 + SpineViewer query 可读
"""
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from ba_modding_toolkit.spine import SkelConverter, SpineViewer, atlas_downgrade, get_skel_version
from conftest import EDIT_SPINE_VERSION, GAME_SPINE_VERSION, SpineAssetSet, bootstrap_spine_assets

if TYPE_CHECKING:
    from conftest import SampleCase


def _require_bootstrap(assets: SpineAssetSet | None) -> SpineAssetSet:
    """自举失败（素材不完整或版本探测/转换失败）时跳过而非误报"""
    if assets is None:
        pytest.skip("素材缺少完整三件套或版本自举失败")
    return assets


@pytest.fixture
def sample_38(
    sample_case: "SampleCase",
    spine_converter_path: Path,
    tmp_path: Path,
) -> SpineAssetSet:
    """自举到 3.8 + spine3 atlas 的三件套副本（本地编辑环境基准）"""
    return _require_bootstrap(
        bootstrap_spine_assets(
            sample_case.assets_dir, EDIT_SPINE_VERSION, spine_converter_path, tmp_path / "sample_38"
        )
    )


@pytest.fixture
def sample_42(
    sample_case: "SampleCase",
    spine_converter_path: Path,
    tmp_path: Path,
) -> SpineAssetSet:
    """自举到 4.2.x 的三件套副本（游戏运行时目标版本基准）"""
    return _require_bootstrap(
        bootstrap_spine_assets(
            sample_case.assets_dir, GAME_SPINE_VERSION, spine_converter_path, tmp_path / "sample_42"
        )
    )


class TestSkelConverter:
    def test_upgrade_38_to_42(
        self,
        sample_38: SpineAssetSet,
        spine_converter_path: Path,
        spine_viewer_path: Path,
        tmp_path: Path,
    ):
        """升级 3.8 → 4.2：转换成功且 query 可读"""
        out_skel = tmp_path / "upgraded.skel"

        # 第一层：subprocess 转换成功
        assert SkelConverter.run(
            sample_38.skel_path, out_skel, spine_converter_path, GAME_SPINE_VERSION
        )

        # 第二层：版本号正确 + SpineViewer 实际可读
        version = get_skel_version(out_skel)
        assert version and version.startswith("4.2")
        ok, info = SpineViewer.query(out_skel, spine_viewer_path)
        assert ok, info
        assert info["animations"]

    def test_downgrade_42_to_38(
        self,
        sample_42: SpineAssetSet,
        spine_converter_path: Path,
        spine_viewer_path: Path,
        tmp_path: Path,
    ):
        """降级 4.2 → 3.8：skel + atlas 配套降级且 query 可读"""
        out_dir = tmp_path / "downgraded"
        out_dir.mkdir()
        out_skel = out_dir / sample_42.skel_path.name

        # 第一层：skel 与 atlas 均降级成功
        assert SkelConverter.run(
            sample_42.skel_path, out_skel, spine_converter_path, EDIT_SPINE_VERSION
        )
        assert atlas_downgrade(sample_42.atlas_path, out_dir)

        # 第二层：版本号正确 + SpineViewer 实际可读
        version = get_skel_version(out_skel)
        assert version and version.startswith("3.8")
        ok, info = SpineViewer.query(out_skel, spine_viewer_path)
        assert ok, info
        assert info["animations"]

    def test_roundtrip(
        self,
        sample_42: SpineAssetSet,
        spine_converter_path: Path,
        tmp_path: Path,
    ):
        """4.2 → 3.8 → 4.2：转换非双射，断言各阶段版本号（major.minor）恢复"""
        down_skel = tmp_path / "roundtrip_38.skel"
        assert SkelConverter.run(
            sample_42.skel_path, down_skel, spine_converter_path, EDIT_SPINE_VERSION
        )
        down_version = get_skel_version(down_skel)
        assert down_version and down_version.startswith("3.8")

        up_skel = tmp_path / "roundtrip_42.skel"
        assert SkelConverter.run(
            down_skel, up_skel, spine_converter_path, GAME_SPINE_VERSION
        )
        up_version = get_skel_version(up_skel)
        assert up_version and up_version.startswith("4.2")

        # roundtrip 恢复到与自举基准一致的 major.minor
        base_version = get_skel_version(sample_42.skel_path)
        assert base_version and up_version.split(".")[:2] == base_version.split(".")[:2]
