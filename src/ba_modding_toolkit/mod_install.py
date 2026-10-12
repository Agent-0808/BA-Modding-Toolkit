# mod_install.py
"""Mod 安装核心逻辑（GUI/CLI 共用）。

包含安装计划数据模型、plan（分析聚类）与 execute（执行替换）流程
"""

from pathlib import Path
from dataclasses import dataclass, field, replace as dc_replace
from enum import StrEnum
import os
import shutil

from .i18n import t
from .utils import no_log
from .models import (
    AnimCheckOptions,
    LogFunc,
    MatchStrategy,
    ParsedFilename,
    ReplaceAssetType,
    SaveOptions,
    SkelConvertOptions,
)
from .bundle import Bundle
from .core import process_mod_update
from .naming import parse_filename
from .searching import search_prefix, _asset_match


# -------- 安装计划数据模型 ---------

class InstallAction(StrEnum):
    """Mod 安装判定动作"""
    DIRECT_REPLACE = "direct_replace"        # 同名存在，直接替换
    UPDATE = "update"                        # 同名不存在，需 search_prefix + process_mod_update
    ALREADY_INSTALLED = "already_installed"  # UPDATE 分支：skip_unchanged 判定所有 asset 未变化
    NOT_FOUND = "not_found"                  # 游戏目录中找不到对应文件
    ERROR = "error"                          # 解析失败 / 冲突等
    MIXED = "mixed"                          # 组内动作混合（仅组级汇总用）

@dataclass
class ModFilePlan:
    """组内单个 mod 文件的安装计划"""
    mod_path: Path
    parsed: ParsedFilename
    action: InstallAction
    existing_path: Path | None = None   # DIRECT_REPLACE：游戏目录中的同名文件
    need_crc_fix: bool = False          # DIRECT_REPLACE：是否需 CRC 碰撞修正（由现有文件平台决定）
    note: str = ""                      # 附加说明（冲突 / 解析失败原因等）

@dataclass
class ModGroup:
    """prefix 聚类后的 mod 安装组（决策与执行以组为单位）"""
    prefix: str
    category: str | None
    core: str
    files: list[ModFilePlan]
    target_paths: list[Path] = field(default_factory=list)  # UPDATE：search_prefix 结果（组级）

    @property
    def group_action(self) -> InstallAction:
        """汇总组动作：全部一致取该值，混合取 MIXED"""
        actions = {f.action for f in self.files}
        if len(actions) == 1:
            return actions.pop()
        return InstallAction.MIXED if actions else InstallAction.ERROR

    @property
    def display_name(self) -> str:
        """弹窗行头展示名"""
        return self.core


# -------- plan（分析聚类） ---------

def _find_same_name_bundles(
    mod_paths: list[Path],
    search_dirs: list[Path],
) -> dict[str, Path]:
    """
    在搜索目录中建立 mod 文件名 → 现有文件的同名索引（单轮 scandir）。

    Args:
        mod_paths: mod 文件路径列表
        search_dirs: 搜索目录列表

    Returns:
        dict[str, Path]: 文件名 → 现有文件路径（同名文件取首个命中目录；
        mod 文件自身位于游戏目录中时不算命中）
    """
    wanted = {p.name: p for p in mod_paths}
    index: dict[str, Path] = {}
    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        with os.scandir(search_dir) as it:
            for entry in it:
                if entry.name not in wanted or entry.name in index:
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                try:
                    if Path(entry.path).samefile(wanted[entry.name]):
                        continue  # mod 自身就在游戏目录中
                except OSError:
                    pass
                index[entry.name] = Path(entry.path)
    return index


def _search_latest_targets(
    source_paths: list[Path],
    search_dirs: list[Path],
    log: LogFunc,
) -> tuple[list[Path], str]:
    """
    按 prefix 搜索候选目标，先过滤至最新日期（多候选自动取 date 最新）再进行资产匹配。

    Returns:
        tuple[list[Path], str]: (匹配的目标路径列表, 错误消息)
    """
    if not source_paths:
        return [], ""

    candidates, err_msg = search_prefix(source_paths[0], search_dirs, log)
    if not candidates:
        return [], err_msg

    latest_date = max(parse_filename(c.name).date for c in candidates)
    filtered = [c for c in candidates if parse_filename(c.name).date == latest_date]
    if len(filtered) != len(candidates):
        log(f'  > {t("log.mod_install.filter_latest_date", date=latest_date)}')

    return _asset_match(source_paths, filtered, log)


def plan_mod_install(
    mod_paths: list[Path],
    game_resource_dir: Path | list[Path],
    log: LogFunc = no_log,
) -> list[ModGroup]:
    """
    分析拖入的 mod 文件，按 (prefix, core) 聚类分组并判定每组与游戏目录的关系。
    纯读操作，不写盘；"已安装相同内容"（skip_unchanged）在执行阶段由
    process_mod_update 判定，此处不基于实际 CRC 做任何对比。

    判定规则（见设计文档 §2.2）：
    - 同名存在 → DIRECT_REPLACE（是否需 CRC 修正由现有文件平台决定）
    - 同名不存在 → UPDATE（search_prefix 搜索，多候选取 date 最新）
    - 搜索不到 → NOT_FOUND；文件名解析失败 → ERROR

    Args:
        mod_paths: 拖入的 mod 文件路径列表
        game_resource_dir: 游戏资源目录（单个或多个）
        log: 日志记录函数

    Returns:
        list[ModGroup]: 聚类后的安装组列表（决策与执行以组为单位）
    """
    search_dirs = [game_resource_dir] if isinstance(game_resource_dir, Path) else game_resource_dir

    log("\n" + "=" * 50)
    log(f"📋 {t('log.mod_install.plan_start', count=len(mod_paths))}")

    # 1. 解析 + 按 (prefix, core) 聚类
    group_map: dict[tuple[str, str], ModGroup] = {}
    for mod_path in mod_paths:
        parsed = parse_filename(mod_path.name)
        if not parsed.core or not parsed.prefix:
            # 解析失败：单文件成组，标记 ERROR
            plan = ModFilePlan(
                mod_path=mod_path,
                parsed=parsed,
                action=InstallAction.ERROR,
                note=t("message.mod_install.filename_parse_failed", filename=mod_path.name),
            )
            group_map[(f"__error__{mod_path}", "")] = ModGroup(
                prefix=parsed.prefix, category=parsed.category,
                core=parsed.core or mod_path.stem, files=[plan],
            )
            continue
        key = (parsed.prefix, parsed.core)
        group = group_map.get(key)
        if group is None:
            group = ModGroup(prefix=parsed.prefix, category=parsed.category, core=parsed.core, files=[])
            group_map[key] = group
        group.files.append(ModFilePlan(mod_path=mod_path, parsed=parsed, action=InstallAction.NOT_FOUND))

    # 2. 同名搜索（单轮 scandir 建立索引）
    name_index = _find_same_name_bundles(mod_paths, search_dirs)

    # 3. 逐组判定
    groups = list(group_map.values())
    for group in groups:
        log("\n" + "-" * 50)
        log(t("log.mod_install.group_info", core=group.core, count=len(group.files)))

        for f in group.files:
            existing = name_index.get(f.mod_path.name)
            if existing is None:
                continue
            f.action = InstallAction.DIRECT_REPLACE
            f.existing_path = existing
            # 是否需 CRC 修正由现有文件的平台决定（StandaloneWindows64 需要碰撞修正）
            f.need_crc_fix = Bundle.check_need_crc(existing, log)
            log(t("log.mod_install.same_name_found", filename=f.mod_path.name))

        update_files = [f for f in group.files if f.action == InstallAction.NOT_FOUND]
        if update_files:
            targets, err_msg = _search_latest_targets(
                [f.mod_path for f in update_files], search_dirs, log,
            )
            if targets:
                group.target_paths = targets
                for f in update_files:
                    f.action = InstallAction.UPDATE
                log(t("log.mod_install.update_targets", count=len(targets),
                      names=", ".join(p.name for p in targets)))
            else:
                for f in update_files:
                    f.note = err_msg
                log(t("log.search.find_failed", message=err_msg))

    # 4. 冲突检测：不同组命中同一目标文件 → 相关组整体标记 ERROR
    target_owner: dict[Path, ModGroup] = {}
    for group in groups:
        for target in group.target_paths:
            owner = target_owner.setdefault(target, group)
            if owner is group:
                continue
            for f in owner.files + group.files:
                if f.action == InstallAction.UPDATE:
                    f.action = InstallAction.ERROR
                    f.note = t("message.mod_install.target_conflict", filename=target.name)
            log(f'  ⚠️ {t("log.mod_install.target_conflict", filename=target.name)}')

    # 5. 汇总
    counts: dict[InstallAction, int] = {}
    for group in groups:
        for f in group.files:
            counts[f.action] = counts.get(f.action, 0) + 1
    log("\n" + t(
        "log.mod_install.plan_done",
        total=len(mod_paths), groups=len(groups),
        direct=counts.get(InstallAction.DIRECT_REPLACE, 0),
        update=counts.get(InstallAction.UPDATE, 0),
        not_found=counts.get(InstallAction.NOT_FOUND, 0),
        error=counts.get(InstallAction.ERROR, 0),
    ))

    return groups


# -------- execute（执行安装） ---------

@dataclass
class InstallResult:
    """execute_mod_install 的返回结果"""
    installed_groups: int = 0                                           # 成功安装组数
    skipped_groups: int = 0                                             # 已安装跳过组数（全部资源未变化）
    failed_groups: list[tuple[str, str]] = field(default_factory=list)  # (组名, 失败原因)
    anim_diffs: dict[str, set[str]] = field(default_factory=dict)       # 动画差异汇总（warning 级，不算失败）


def _backup_and_replace(src: Path, dst: Path, create_backup: bool, log: LogFunc) -> bool:
    """备份并替换文件（.backup 后缀约定与 GUI replace_file 一致）"""
    try:
        if create_backup:
            backup_path = dst.with_suffix(dst.suffix + ".backup")
            shutil.copy2(dst, backup_path)
            log(t("log.file.backed_up", path=backup_path))
        log(t("log.file.overwritten", path=dst))
        shutil.copy2(src, dst)
        return True
    except Exception as e:
        log(f"❌ {t('log.mod_install.replace_failed', path=dst, error=e)}")
        return False


def _direct_replace(f: ModFilePlan, save_options: SaveOptions, create_backup: bool, log: LogFunc) -> bool:
    """DIRECT_REPLACE 执行：需 CRC 碰撞修正时重存临时文件后替换，否则纯拷贝（§2.2）"""
    if not f.need_crc_fix:
        return _backup_and_replace(f.mod_path, f.existing_path, create_backup, log)

    tmp_path = f.existing_path.with_name(f.existing_path.stem + ".mod_install_tmp")
    try:
        bundle = Bundle.load(f.mod_path, log)
        if bundle is None:
            log(f"❌ {t('message.load_failed')}: {f.mod_path.name}")
            return False
        ok, msg = bundle.save(tmp_path, dc_replace(save_options, perform_crc=True))
        if not ok:
            log(f"❌ {t('log.file.save_failed', path=tmp_path, error=msg)}")
            return False
        return _backup_and_replace(tmp_path, f.existing_path, create_backup, log)
    finally:
        tmp_path.unlink(missing_ok=True)


def execute_mod_install(
    groups: list[ModGroup],
    output_dir: Path,
    asset_types_to_replace: set[ReplaceAssetType],
    save_options: SaveOptions,
    spine_options: SkelConvertOptions | None = None,
    match_strategy: MatchStrategy = 'cont_name_type',
    anim_check: AnimCheckOptions | None = None,
    create_backup: bool = True,
    log: LogFunc = no_log,
) -> InstallResult:
    """
    按用户决策逐组执行安装（见设计文档 §6）。

    - DIRECT_REPLACE：备份 → 需要时 CRC 碰撞修正重存后替换，否则纯拷贝
    - UPDATE：process_mod_update（skip_unchanged=True）生成后备份替换；
      全部资源未变化 → 该组视为已安装跳过
    - 单组失败不影响后续组；动画差异仅警告不视为失败

    Args:
        groups: 待安装的组列表（调用方已过滤决策与可安装性）
        output_dir: UPDATE 生成文件的输出目录
        asset_types_to_replace: 需要替换的资源类型集合
        save_options: 保存与 CRC 修正选项（UPDATE 分支使用）
        spine_options: Spine 版本转换选项
        match_strategy: 匹配策略
        anim_check: 动画差异检测选项
        create_backup: 是否创建 .backup 备份
        log: 日志记录函数

    Returns:
        InstallResult: 组级成功/跳过/失败统计与失败明细
    """
    result = InstallResult()
    output_dir.mkdir(parents=True, exist_ok=True)

    for group in groups:
        direct_files = [f for f in group.files if f.action == InstallAction.DIRECT_REPLACE]
        update_files = [f for f in group.files if f.action == InstallAction.UPDATE]
        if not direct_files and not update_files:
            continue

        log("\n" + "-" * 50)
        log(t("log.mod_install.execute_group", core=group.core))

        group_failed = False
        all_unchanged = True

        # 1. DIRECT_REPLACE：同名直接替换
        for f in direct_files:
            if f.need_crc_fix:
                log(t("log.mod_install.crc_resave", filename=f.mod_path.name))
            if not _direct_replace(f, save_options, create_backup, log):
                result.failed_groups.append((group.core, f.mod_path.name))
                group_failed = True

        # 2. UPDATE：process_mod_update 生成后备份替换
        if update_files:
            update_result = process_mod_update(
                source_paths=[f.mod_path for f in update_files],
                target_paths=group.target_paths,
                output_dir=output_dir,
                asset_types_to_replace=asset_types_to_replace,
                save_options=save_options,
                spine_options=spine_options,
                skip_unchanged=True,
                match_strategy=match_strategy,
                anim_check=anim_check,
                log=log,
            )
            if not update_result.success:
                # skel 版本冲突等：本组中止，继续后续组
                result.failed_groups.append((group.core, update_result.message))
                group_failed = True
            elif update_result.message == "all_targets_unchanged":
                log(t("log.mod_install.already_installed", core=group.core))
            else:
                for pair in update_result.file_pairs:
                    # FilePair: output = 生成文件，source = 游戏目录原文件
                    if not _backup_and_replace(pair.output, pair.source, create_backup, log):
                        result.failed_groups.append((group.core, pair.source.name))
                        group_failed = True
                all_unchanged = False
                for name, anims in (update_result.anim_diffs or {}).items():
                    result.anim_diffs.setdefault(name, set()).update(anims)

        # 3. 组级统计（MIXED 组：直接替换已生效时仍按实际结果计）
        if group_failed:
            continue
        if all_unchanged and not direct_files:
            result.skipped_groups += 1
        else:
            result.installed_groups += 1

    log("\n" + t(
        "log.mod_install.execute_done",
        installed=result.installed_groups,
        skipped=result.skipped_groups,
        failed=len(result.failed_groups),
    ))
    return result
