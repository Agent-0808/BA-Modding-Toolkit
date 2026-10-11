"""SpineViewerCLI 单元级测试：query / render。

外部工具缺失时自动跳过；直接使用 sample 三件套原始素材（版本不固定，
SpineViewer 3.x/4.x skel 均可读取）。
"""
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from PIL import Image

from ba_modding_toolkit.spine import SpineViewer
from conftest import require_render_support

if TYPE_CHECKING:
    from conftest import SampleCase

# 渲染结果受 SpineViewer 版本影响，仅断言"尺寸合理 + 非纯空白"
MIN_RENDER_SIZE = 32


def _require_skel(sample_case: "SampleCase") -> Path:
    if sample_case.skel_path is None:
        pytest.skip("素材缺少 .skel")
    return sample_case.skel_path


class TestSpineViewer:
    def test_query(self, sample_case: "SampleCase", spine_viewer_path: Path):
        """query 返回 (True, dict)，animations 非空且为列表"""
        skel_path = _require_skel(sample_case)

        ok, info = SpineViewer.query(skel_path, spine_viewer_path)
        assert ok, info
        animations = info.get("animations")
        assert isinstance(animations, list)
        assert animations

    def test_render(
        self,
        sample_case: "SampleCase",
        spine_viewer_path: Path,
        tmp_path: Path,
    ):
        """render 输出 png 存在、尺寸合理、非纯空白"""
        require_render_support()
        skel_path = _require_skel(sample_case)
        out_png = tmp_path / "preview.png"

        ok, msg = SpineViewer.render_preview(skel_path, out_png, spine_viewer_path)
        assert ok, msg
        assert out_png.exists()

        img = Image.open(out_png).convert("RGBA")
        assert img.width >= MIN_RENDER_SIZE and img.height >= MIN_RENDER_SIZE
        # 存在非透明像素（透明背景下渲染出实际内容）
        assert img.getchannel("A").getextrema()[1] > 0