"""Spine2Dump 测试：_parse_inspect 解析 / select_animation / query / render_preview / 动画差异检测。

spine2dump 基于单一 spine-c 4.x 运行时，仅支持 4.x skel；3.8（降级产物）加载失败
是当前 v100 构建的预期行为（test_query_38_unsupported），上游若支持 3.8 需同步调整。

render_preview 的双后端一致性验证见 TestBackendAgreement（仅断言双方均成功，
像素级对比因尺寸语义差异（上限 vs 放大至充满）不做强断言，人工目检用
.trae/scripts/compare_backends.py）。
"""
from pathlib import Path

import pytest
from PIL import Image

from ba_modding_toolkit.spine import (
    RENDER_PRESET_LOW,
    Spine2Dump,
    SpineViewer,
    check_skel_animation_diff,
    get_skel_version,
    select_animation,
)
from conftest import collect_sample_cases, require_render_support

# 渲染结果受后端实现影响，仅断言"尺寸合理 + 非纯空白"
MIN_RENDER_SIZE = 32

# 真实 inspect 输出样本（miyu 素材，已裁剪表格行，保留各区段结构）
SAMPLE_INSPECT_OUTPUT = """\
Spine2D 4.2 load result
┌────────────┬──────────────────────────────────────────────────────┐
│ skeleton   │ CH0145_spr.skel                                      │
│ atlas      │ CH0145_spr.atlas                                     │
│ version    │ 4.2.33                                               │
│ bounds     │ -364.00 -941.00 1084.80 2302.00                      │
│ bones      │ 4                                                    │
│ slots      │ 12                                                   │
│ skins      │ 2                                                    │
│ animations │ 16                                                   │
└────────────┴──────────────────────────────────────────────────────┘
Animations (2)
┌──────────────┬──────────┐
│ name         │ duration │
├──────────────┼──────────┤
│ 00           │ 3.333s   │
│ Idle_01      │ 3.333s   │
└──────────────┴──────────┘
Skins (2)
├─ default
│   ├─ halo_02/halo_02
│   └─ 01_normal/01_normal
└─ Diorama
    └─ Diorama/Diorama2
Expression candidates
┌─────────┬──────────┬────────────┐
│ skin    │ slot     │ attachment │
├─────────┼──────────┼────────────┤
│ default │ eyeclose │ eyeclose   │
└─────────┴──────────┴────────────┘
"""


def _find_sample_skel_by_version(prefix: str) -> Path | None:
    """在 sample 案例中查找第一个指定版本的 skel（数据不入 git，缺失返回 None）"""
    for case in collect_sample_cases():
        if case.skel_path is None:
            continue
        version = get_skel_version(case.skel_path)
        if version and version.startswith(prefix):
            return case.skel_path
    return None


@pytest.fixture(scope="session")
def skel_42() -> Path:
    """sample 中的 4.x skel（spine2dump 可加载）"""
    skel = _find_sample_skel_by_version("4.")
    if skel is None:
        pytest.skip("sample 中无 4.x skel 素材")
    return skel


@pytest.fixture(scope="session")
def skel_38() -> Path:
    """sample 中的 3.x skel（spine2dump 不可加载）"""
    skel = _find_sample_skel_by_version("3.")
    if skel is None:
        pytest.skip("sample 中无 3.x skel 素材")
    return skel


class TestParseInspect:
    def test_parse_sample_output(self):
        """真实 inspect 输出解析：动画取表格首列，皮肤仅取深度 0 行"""
        info = Spine2Dump._parse_inspect(SAMPLE_INSPECT_OUTPUT)
        assert info["animations"] == ["00", "Idle_01"]
        assert info["skins"] == ["default", "Diorama"]

    def test_parse_empty(self):
        """无表格输出时返回空结构"""
        assert Spine2Dump._parse_inspect("no tables here") == {"animations": [], "skins": []}


class TestSelectAnimation:
    def test_prefers_idle(self):
        assert select_animation(["01", "Idle_01", "Dummy"]) == "Idle_01"

    def test_fallback_dummy(self):
        assert select_animation(["01", "Dummy"]) == "Dummy"

    def test_fallback_first(self):
        assert select_animation(["01", "02"]) == "01"

    def test_empty(self):
        assert select_animation([]) is None


class TestSpine2Dump:
    def test_query_42(self, skel_42: Path, spine2dump_path: Path):
        """4.x skel query 成功：animations 非空且为列表，skins 非空"""
        ok, info = Spine2Dump(spine2dump_path).query(skel_42)
        assert ok, info
        assert isinstance(info.get("animations"), list)
        assert info["animations"]
        assert info["skins"]

    def test_query_38_unsupported(self, skel_38: Path, spine2dump_path: Path):
        """3.x skel 加载失败（v100 spine-c 运行时仅支持 4.x），失败而非崩溃"""
        ok, _ = Spine2Dump(spine2dump_path).query(skel_38)
        assert not ok

    def test_render_preview_42(self, skel_42: Path, spine2dump_path: Path, tmp_path: Path):
        """4.x skel render_preview 输出 png 存在、尺寸合理、非纯空白"""
        require_render_support()
        out_png = tmp_path / "preview.png"

        ok, msg = Spine2Dump(spine2dump_path).render_preview(skel_42, out_png, render_options=RENDER_PRESET_LOW)
        assert ok, msg
        assert out_png.exists()

        img = Image.open(out_png).convert("RGBA")
        assert img.width >= MIN_RENDER_SIZE and img.height >= MIN_RENDER_SIZE
        assert img.getchannel("A").getextrema()[1] > 0

    def test_render_preview_large(self, large_skel_path: Path, spine2dump_path: Path, tmp_path: Path):
        """大型素材（4 页 atlas）render_preview 成功，覆盖多页 atlas 分支"""
        require_render_support()
        out_png = tmp_path / "preview.png"

        ok, msg = Spine2Dump(spine2dump_path).render_preview(large_skel_path, out_png, render_options=RENDER_PRESET_LOW)
        assert ok, msg

        img = Image.open(out_png).convert("RGBA")
        assert img.width >= MIN_RENDER_SIZE and img.height >= MIN_RENDER_SIZE


class TestAnimDiff:
    def test_diff_same_bytes(self, skel_42: Path, spine2dump_path: Path):
        """bytes 目标与来源相同（含 atlas_text 占位写入路径）时无新增动画"""
        backend = Spine2Dump(spine2dump_path)
        atlas_text = skel_42.with_suffix(".atlas").read_text(encoding="utf-8")
        assert check_skel_animation_diff(skel_42, skel_42.read_bytes(), backend, atlas_text=atlas_text) == []

    def test_diff_between_skels(self, skel_42: Path, large_skel_path: Path, spine2dump_path: Path):
        """两个不同 skel 的差异与 query 结果的集合差一致"""
        backend = Spine2Dump(spine2dump_path)
        _, info_src = backend.query(skel_42)
        _, info_tgt = backend.query(large_skel_path)
        expected = sorted(set(info_tgt["animations"]) - set(info_src["animations"]))
        assert check_skel_animation_diff(skel_42, large_skel_path, backend) == expected


class TestBackendAgreement:
    def test_render_both_backends(self, skel_42: Path, spine_viewer_path: Path,
                                  spine2dump_path: Path, tmp_path: Path):
        """同一 skel 双后端渲染均成功（像素级对比依赖人工目检脚本）"""
        require_render_support()
        ok_viewer, msg_viewer = SpineViewer(spine_viewer_path).render_preview(
            skel_42, tmp_path / "viewer.png", render_options=RENDER_PRESET_LOW)
        ok_dump, msg_dump = Spine2Dump(spine2dump_path).render_preview(
            skel_42, tmp_path / "dump.png", render_options=RENDER_PRESET_LOW)
        assert ok_viewer, msg_viewer
        assert ok_dump, msg_dump
