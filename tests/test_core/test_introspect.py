# 内省层测试：inspect/trace 的数据层行为（不依赖输出文本格式）
#
# 直接测 core 层数据函数与对象图解析闭环；每个测试先校验素材是否满足
# 测试前提（可加载 / 具名 / 有引用），不满足则跳过——与"素材缺失自动跳过"约定一致。

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from ba_modding_toolkit.bundle import Bundle
from ba_modding_toolkit.core.introspect import _collect_externals, _make_graph, _self_cabs
from ba_modding_toolkit.references import iter_pptrs
from ba_modding_toolkit.utils import no_log

if TYPE_CHECKING:
    from conftest import RessRegressCase, SampleCase


def _load(path: Path) -> Bundle:
    bundle = Bundle.load(path)
    if bundle is None:
        pytest.skip("bundle 无法加载（不符合测试前提）")
    return bundle


def _first_obj(bundle: Bundle, type_name: str):
    return next((o for o in bundle.env.objects if o.type.name == type_name), None)


class TestSelfCabs:
    def test_matches_env_assets(self, sample_case: "SampleCase") -> None:
        """_self_cabs 返回 env.assets 全部具名 SerializedFile（按序）"""
        bundle = _load(sample_case.bundle_paths[0])
        expected = [n for n in (getattr(sf, "name", "") for sf in bundle.env.assets) if n]
        if not expected:
            pytest.skip("bundle 无具名 SerializedFile（不符合测试前提）")
        assert _self_cabs(bundle) == expected


class TestCollectExternals:
    def test_lists_all_externals(self, ress_regress_case: "RessRegressCase") -> None:
        """_collect_externals 覆盖 env.assets 的全部外部引用，且已归一为纯文件名"""
        bundle = _load(ress_regress_case.original_path)
        expected = [
            ext.path.replace("\\", "/").rsplit("/", 1)[-1]
            for sf in bundle.env.assets
            for ext in sf.externals
        ]
        if not expected:
            pytest.skip("bundle 无外部引用（不符合测试前提）")
        result = _collect_externals(bundle)
        assert result == set(expected)
        assert all(cab and "/" not in cab for cab in result)


class TestGraphResolution:
    def test_same_file_refs_resolve_in_bundle(self, sample_case: "SampleCase") -> None:
        """local-only 下 AssetBundle 对象的 PPtr 引用经对象图解析回本 bundle 内对象"""
        bundle = _load(sample_case.bundle_paths[0])
        target = _first_obj(bundle, "AssetBundle")
        if target is None:
            pytest.skip("bundle 无 AssetBundle 对象（不符合测试前提）")

        graph = _make_graph([bundle], [], no_log, None)
        refs = [p for p in iter_pptrs(graph.tree(target)) if p.get("m_PathID")]
        if not refs:
            pytest.skip("AssetBundle 对象无有效引用（不符合测试前提）")

        self_cabs = {c.lower() for c in _self_cabs(bundle)}
        for ptr in refs:
            resolved = graph.deref(target, ptr)
            assert resolved is not None, f"指针未解析: {ptr}"
            assert resolved.assets_file.name.lower() in self_cabs
