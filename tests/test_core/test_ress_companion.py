# 回归测试：mod update 后 .resS/.resource 流引用必须闭合（companion 修复）
#
# 背景：raw dump（get_raw_data/set_raw_data 路径）只含序列化对象头，
# 流式数据引用（m_StreamData/m_Resource）内嵌源 bundle 的 CAB 哈希名。
# 目标 bundle（游戏更新后重新打包）CAB 名必然不同 → 悬空引用 → 游戏内资源丢失。
# 真实案例：yuuka mod update 后角色本体（内联 Mesh）正常，但 Halo（流式 Mesh）无法显示。
#
# 修复方案：extract_patch 时把 raw 内容引用的源 .resS/.resource 作为 companion 随 patch 走，
# apply_patch 时附加到目标 bundle（env.file.get_writeable_cab）。
#
# 测试数据：tests/assets/ress_regress/<case_name>/mod/*.bundle 与 original/*.bundle(.backup)，
# 案例由 conftest.collect_ress_regress_cases 自动发现并参数化，新增案例无需改代码。
#
# 注意：本文件测试为 TDD 红基线——companion 修复实现前，测试预期失败（悬空引用）
# 实现后应全部通过。

import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import UnityPy
from UnityPy.helpers.ResourceReader import get_resource_data

from ba_modding_toolkit.core import process_mod_update
from ba_modding_toolkit.models import SaveOptions
from ba_modding_toolkit.bundle import Bundle

if TYPE_CHECKING:
    from conftest import RessRegressCase

# 对象序列化数据中的流引用（m_StreamData.path / m_Resource.m_Source 的 basename）
_RE_STREAM_REF = re.compile(rb"[A-Za-z0-9_\-]+\.(?:resS|resource)")
# 流引用完整路径前缀 archive:/<SerializedFile名>/<文件名>，<SF名> 段必须与目标 bundle 的 SF 名一致
# （UnityPy 按 basename 兜底解析，游戏引擎校验前缀段——实装输出 halo 不可见的根因）
_RE_STREAM_REF_PREFIX = re.compile(rb"archive:/([A-Za-z0-9_\-]+)/[A-Za-z0-9_\-]+\.(?:resS|resource)")


def assert_stream_refs_resolve(bundle_path: Path, watched_type: str = "Mesh") -> None:
    """断言 bundle 内所有对象的流引用都能在 bundle 内部解析（无悬空引用）。

    三级验证：
    1. 名称级：raw 数据中引用的 .resS/.resource basename 必须存在于内部文件；
    2. 前缀级：archive:/<SF名>/ 前缀段必须等于本 bundle 的 SerializedFile 名
       （游戏运行时要求，对应当年正常 mod（前缀=自身SF名）与实装输出（前缀=源SF名）的对比结论）；
    3. 数据级：对流式对象实际调用 ResourceReader.get_resource_data 验证可读。
    """
    env = UnityPy.load(str(bundle_path))
    internal = {
        name
        for name, f in env.file.files.items()
        if not hasattr(f, "objects")
    }
    sf_names = {
        name
        for name, f in env.file.files.items()
        if hasattr(f, "objects")
    }

    dangling: list[str] = []
    streamed_checked = 0
    for obj in env.objects:
        if obj.type.name != watched_type:
            continue
        raw = obj.get_raw_data()
        refs = {r.decode() for r in _RE_STREAM_REF.findall(raw)}
        name = obj.peek_name() or f"path_id:{obj.path_id}"
        missing = refs - internal
        if missing:
            dangling.append(f"{name} 引用 {sorted(missing)} 不在 bundle 内")
            continue
        # 前缀级：SF 名段必须属于本 bundle 的 SerializedFile（单 SF bundle 即等于自身 SF 名）
        prefixes = {m.group(1).decode() for m in _RE_STREAM_REF_PREFIX.finditer(raw)}
        bad_prefix = prefixes - sf_names
        if bad_prefix:
            dangling.append(f"{name} 流引用前缀 {sorted(bad_prefix)} 与 SF 名 {sorted(sf_names)} 不一致")
            continue
        # 名称闭合后做实际解析验证（仅流式对象，typetree 头小解析快）
        if refs:
            tree = obj.read_typetree(wrap=False)
            sd = tree.get("m_StreamData") or tree.get("m_Resource")
            # m_StreamData 键为 offset/size；m_Resource 键为 m_Offset/m_Size（offset 可为 0，不能用 or 链）
            offset = sd["offset"] if "offset" in sd else sd["m_Offset"]
            size = sd["size"] if "size" in sd else sd["m_Size"]
            path = sd.get("path") or sd.get("m_Source")
            get_resource_data(path, obj.assets_file, offset, size)
            streamed_checked += 1

    assert not dangling, f"存在悬空流引用: {dangling}"
    assert streamed_checked > 0, f"未找到流式 {watched_type} 对象，测试数据可能不完整"


def _run_mod_update(mod_path: Path, original_path: Path, output_dir: Path) -> Path:
    """执行 mod update（Mesh raw 路径），返回输出文件路径"""
    result = process_mod_update(
        source_paths=[mod_path],
        target_paths=[original_path],
        output_dir=output_dir,
        asset_types_to_replace={"Mesh"},
        save_options=SaveOptions(perform_crc=False, compression="none"),
        match_strategy="path_id",
    )
    assert result.success, f"mod update 失败: {result.message}"
    assert result.file_pairs, "mod update 未产生输出文件"
    return result.file_pairs[0].output


def _build_sim_version_b(source: Path, output_path: Path) -> None:
    """构造模拟"新版本"文件：内部 CAB 哈希等长改名（模拟游戏更新重新打包）。

    真实游戏更新必然产生新 CAB 名；等长替换保证序列化布局不变，结构自洽。
    """
    env = UnityPy.load(str(source))
    # 从内部附属文件名提取 CAB 哈希（如 CAB-3b0fa0...resS → 3b0fa0...）
    hashes = {
        name.split(".", 1)[0][4:]
        for name, f in env.file.files.items()
        if not hasattr(f, "objects") and name.startswith("CAB-")
    }
    assert hashes, "源文件不含 .resS/.resource 附属文件，无法构造模拟版本"

    renamed = {h: ("f" * len(h)) for h in hashes}

    def rename_cab(name: str) -> str:
        for old, new in renamed.items():
            if old in name:
                return name.replace(old, new)
        return name

    for obj in env.objects:
        raw = obj.get_raw_data()
        if any(h.encode() in raw for h in hashes):
            for old, new in renamed.items():
                raw = raw.replace(old.encode(), new.encode())
            obj.set_raw_data(raw)
    env.file.files = {rename_cab(name): f for name, f in env.file.files.items()}
    output_path.write_bytes(env.file.save(packer="none"))


def test_mod_update_stream_refs_resolve(ress_regress_case: "RessRegressCase", tmp_path: Path) -> None:
    """真实案例：mod 文件 update 到原文件，输出流引用必须闭合。

    修复后：输出 bundle 内所有 Mesh 流引用必须闭合且流数据可实际读取。
    """
    output = _run_mod_update(ress_regress_case.mod_path, ress_regress_case.original_path, tmp_path)
    assert_stream_refs_resolve(output)


def test_sim_version_b_mod_update_stream_refs_resolve(ress_regress_case: "RessRegressCase", tmp_path: Path) -> None:
    """合成案例：mod 文件 update 到"新版本"目标（原文件 CAB 整体改名）。

    即使被替换的流式对象内容完全相同，仅因 CAB 改名就会悬空——
    证明失效与内容无关，是引用宿主问题。
    """
    sim_b = tmp_path / "sim_version_b.bundle"
    _build_sim_version_b(ress_regress_case.original_path, sim_b)

    # 自检：模拟目标文件结构自洽（改名后流数据可解析）
    assert_stream_refs_resolve(sim_b)

    output = _run_mod_update(ress_regress_case.mod_path, sim_b, tmp_path)
    assert_stream_refs_resolve(output)
