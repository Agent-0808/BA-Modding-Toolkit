"""外部工具参与的端到端集成测试：mod update / asset packing / asset extractor。

外部工具缺失时自动跳过；update_case 与 sample_case 内 skel 版本未知，
测试中动态探测并取不同的 preset 版本，保证转换路径必被触发。
"""
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PIL import Image

from ba_modding_toolkit.core import (
    SaveOptions,
    _extract_assets_from_bundle,
    process_asset_packing,
    process_mod_update,
    render_spine_preview_from_bundle,
)
from ba_modding_toolkit.models import AnimCheckOptions, SkelConvertOptions
from ba_modding_toolkit.spine import SpineViewer, get_skel_version
from conftest import EDIT_SPINE_VERSION, GAME_SPINE_VERSION, require_render_support

if TYPE_CHECKING:
    from conftest import SampleCase, UpdateCase

# 渲染结果受 SpineViewer 版本影响，仅断言"尺寸合理 + 非纯空白"
MIN_RENDER_SIZE = 32

# 与现有 core 测试一致的保存选项：不修正 CRC、不压缩，聚焦流程本身
_SAVE_OPTIONS = SaveOptions(perform_crc=False, compression="none")


def _pick_alternate_version(current: str) -> str:
    """取与当前版本不同的 preset 目标版本，保证版本转换路径被触发"""
    return EDIT_SPINE_VERSION if current.startswith("4.2") else GAME_SPINE_VERSION


def _major_minor(version: str) -> str:
    return ".".join(version.split(".")[:2])


class TestExternalCoreIntegration:
    def test_mod_update_anim_check(
        self,
        update_case: "UpdateCase",
        spine_viewer_path: Path,
        tmp_path: Path,
    ):
        """mod update + 动画检测：成功且 anim_diffs 为按 skel 名归类的映射"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = process_mod_update(
            source_paths=update_case.old_paths,
            target_paths=update_case.new_paths,
            output_dir=output_dir,
            asset_types_to_replace={"Texture2D", "TextAsset"},
            save_options=_SAVE_OPTIONS,
            anim_check=AnimCheckOptions(enabled=True, viewer_path=spine_viewer_path),
        )

        assert result.success is True, result.message
        assert result.anim_diffs is not None
        for anims in result.anim_diffs.values():
            assert isinstance(anims, list)

    def test_mod_update_skel_convert(
        self,
        update_case: "UpdateCase",
        spine_converter_path: Path,
        tmp_path: Path,
    ):
        """mod update + 版本转换：输出 bundle 内 skel 版本 == preset"""
        # 动态探测 old mod 内 skel 版本，preset 取不同值保证转换必被触发
        probe_dir = tmp_path / "probe"
        probe_dir.mkdir()
        _extract_assets_from_bundle(update_case.old_paths, probe_dir, {"TextAsset"})
        probe_skels = list(probe_dir.glob("*.skel"))
        if not probe_skels:
            pytest.skip("旧 mod 中无 skel 资源")
        current = get_skel_version(probe_skels[0])
        assert current, "skel 版本探测失败"
        target = _pick_alternate_version(current)

        output_dir = tmp_path / "output"
        output_dir.mkdir()
        result = process_mod_update(
            source_paths=update_case.old_paths,
            target_paths=update_case.new_paths,
            output_dir=output_dir,
            asset_types_to_replace={"Texture2D", "TextAsset"},
            save_options=_SAVE_OPTIONS,
            spine_options=SkelConvertOptions(
                enabled=True, converter_path=spine_converter_path, target_version=target
            ),
        )

        assert result.success is True, result.message
        assert result.file_pairs

        # 从输出 bundle 提取 skel 验证版本
        out_extract = tmp_path / "out_extract"
        out_extract.mkdir()
        _extract_assets_from_bundle(
            [pair.output for pair in result.file_pairs], out_extract, {"TextAsset"}
        )
        assert list(out_extract.glob("*.skel")), "输出 bundle 中未找到 skel"
        for out_skel in out_extract.glob("*.skel"):
            version = get_skel_version(out_skel)
            assert version and version.startswith(_major_minor(target)), out_skel.name

    def test_asset_packing_skel_convert(
        self,
        sample_case: "SampleCase",
        spine_converter_path: Path,
        spine_viewer_path: Path,
        tmp_path: Path,
    ):
        """asset packing + 版本转换：打包成功、输出 skel 版本正确且 query 可读"""
        assert sample_case.skel_path is not None
        current = get_skel_version(sample_case.skel_path)
        assert current, "素材 skel 版本探测失败"
        target = _pick_alternate_version(current)

        output_dir = tmp_path / "packed"
        output_dir.mkdir()
        ok, msg, pairs = process_asset_packing(
            target_bundle_path=sample_case.bundle_paths,
            assets=[sample_case.assets_dir],
            output_dir=output_dir,
            save_options=_SAVE_OPTIONS,
            spine_options=SkelConvertOptions(
                enabled=True, converter_path=spine_converter_path, target_version=target
            ),
            skip_unchanged=False,
        )

        assert ok, msg
        assert pairs

        # 从输出 bundle 提取同名 skel 验证版本 + viewer query 可读
        out_extract = tmp_path / "out_extract"
        out_extract.mkdir()
        _extract_assets_from_bundle([pair.output for pair in pairs], out_extract, {"TextAsset"})
        packed_skel = out_extract / sample_case.skel_path.name
        assert packed_skel.exists(), "输出 bundle 中未找到同名 skel"

        version = get_skel_version(packed_skel)
        assert version and version.startswith(_major_minor(target))
        query_ok, info = SpineViewer.query(packed_skel, spine_viewer_path)
        assert query_ok
        assert info["animations"]

    def test_extractor_spine_preview(
        self,
        sample_case: "SampleCase",
        spine_viewer_path: Path,
        tmp_path: Path,
    ):
        """asset extractor + spine preview：从 bundle 渲染预览图存在且非空白"""
        require_render_support()
        ok, msg, rendered = render_spine_preview_from_bundle(
            sample_case.bundle_paths, tmp_path / "preview", spine_viewer_path
        )

        assert ok, msg
        assert rendered
        for png in rendered:
            assert png.exists()
            img = Image.open(png).convert("RGBA")
            assert img.width >= MIN_RENDER_SIZE and img.height >= MIN_RENDER_SIZE
            assert img.getchannel("A").getextrema()[1] > 0