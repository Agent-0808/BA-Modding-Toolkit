from pathlib import Path
import shutil
from typing import TYPE_CHECKING

from ba_modding_toolkit.mod_install import plan_mod_install, InstallAction
from ba_modding_toolkit.bundle import Bundle

if TYPE_CHECKING:
    from conftest import UpdateCase

# 案例数据缺失时 conftest 参数化为空参数集，测试自动跳过
class TestPlanModInstall:
    def test_direct_replace(self, update_case: "UpdateCase", tmp_path: Path):
        """同名存在 → DIRECT_REPLACE，existing_path 指向游戏目录中的文件"""
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        for p in update_case.new_paths:
            shutil.copy2(p, game_dir / p.name)

        groups = plan_mod_install(update_case.new_paths, game_dir)

        assert len(groups) == 1
        group = groups[0]
        assert group.group_action == InstallAction.DIRECT_REPLACE
        assert len(group.files) == len(update_case.new_paths)
        for f in group.files:
            assert f.action == InstallAction.DIRECT_REPLACE
            assert f.existing_path is not None
            assert f.existing_path.name == f.mod_path.name
            assert isinstance(f.need_crc_fix, bool)
        assert not group.target_paths

    def test_update(self, update_case: "UpdateCase", tmp_path: Path):
        """同名不存在但 prefix 可匹配新版文件 → UPDATE，多候选取最新日期"""
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        for p in update_case.new_paths:
            shutil.copy2(p, game_dir / p.name)

        groups = plan_mod_install(update_case.old_paths, game_dir)

        assert len(groups) == 1
        group = groups[0]
        assert group.group_action == InstallAction.UPDATE
        assert group.target_paths
        for f in group.files:
            assert f.action == InstallAction.UPDATE
            assert f.existing_path is None

    def test_mixed_group(self, update_case: "UpdateCase", tmp_path: Path):
        """新旧 mod 混合拖入：同名存在的直接替换，缺失的走更新 → 组级 MIXED"""
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        for p in update_case.new_paths:
            shutil.copy2(p, game_dir / p.name)

        mod_paths = update_case.old_paths + update_case.new_paths
        groups = plan_mod_install(mod_paths, game_dir)

        # 同 prefix + core → 聚为一组
        assert len(groups) == 1
        group = groups[0]
        assert group.group_action == InstallAction.MIXED
        assert group.target_paths
        actions = {f.action for f in group.files}
        assert actions == {InstallAction.DIRECT_REPLACE, InstallAction.UPDATE}

    def test_not_found(self, update_case: "UpdateCase", tmp_path: Path):
        """游戏目录为空 → NOT_FOUND"""
        game_dir = tmp_path / "game"
        game_dir.mkdir()

        groups = plan_mod_install(update_case.old_paths, game_dir)

        assert len(groups) == 1
        assert groups[0].group_action == InstallAction.NOT_FOUND
        assert groups[0].files[0].action == InstallAction.NOT_FOUND

    def test_parse_error(self, tmp_path: Path):
        """文件名无法解析（无日期中轴）→ 单文件成组，ERROR"""
        bad = tmp_path / "not_a_bundle.png"
        bad.write_bytes(b"")

        groups = plan_mod_install([bad], tmp_path)

        assert len(groups) == 1
        assert groups[0].group_action == InstallAction.ERROR
        assert groups[0].files[0].action == InstallAction.ERROR
        assert groups[0].files[0].note

    def test_trailing_bytes_eof_guard(self, tmp_path: Path):
        """回归：空文件/损坏文件不应导致 get_trailing_bytes 死循环（EOF 守卫）"""
        empty = tmp_path / "empty.bundle"
        empty.write_bytes(b"")
        assert Bundle.get_trailing_bytes(empty) is None
        assert Bundle.check_need_crc(empty) is False
