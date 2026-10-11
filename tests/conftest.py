import os
import shutil
import tomllib
import pytest
from pathlib import Path
from typing import NamedTuple
from PIL import Image

from ba_modding_toolkit.spine import SkelConverter, atlas_downgrade, get_skel_version
from ba_modding_toolkit.utils import LogFunc, no_log

# 测试数据统一约定（数据文件不入 git，仅 .gitkeep 跟踪目录结构）。
# 目录按数据扮演的角色命名，不绑定具体角色素材；每组下按案例子目录组织，
# 案例自动发现并参数化——新增多组数据只需复制案例目录，无需改代码：
#   assets/sample/<case>/{assets,bundles}         散装资源 + 配套 bundle
#   assets/mod_update/<case>/{old,new}            旧 mod bundle + 新原版 bundle
#                                                 （bundle 文件名必须保持可被
#                                                   parse_filename 解析的完整命名）
#   assets/legacy_rename/<case>/{assets,bundles}  磁盘旧命名资源 + 新 bundle
#   assets/ress_regress/<case>/{mod,original}     流引用回归案例
# 数据缺失时案例列表为空，引用案例 fixture 的测试自动跳过。
ASSETS_DIR = Path(__file__).parent / "assets"

SAMPLE_DIR = ASSETS_DIR / "sample"
MOD_UPDATE_DIR = ASSETS_DIR / "mod_update"
LEGACY_RENAME_DIR = ASSETS_DIR / "legacy_rename"
RESS_REGRESS_DIR = ASSETS_DIR / "ress_regress"


class SampleCase(NamedTuple):
    """sample 组案例：散装资源目录 + 配套 bundle 文件"""
    name: str
    assets_dir: Path
    bundle_paths: list[Path]

    @property
    def image_path(self) -> Path | None:
        return find_first_file(self.assets_dir, ".png")

    @property
    def skel_path(self) -> Path | None:
        return find_first_file(self.assets_dir, ".skel")

    @property
    def atlas_path(self) -> Path | None:
        return find_first_file(self.assets_dir, ".atlas")


class UpdateCase(NamedTuple):
    """mod_update 组案例：旧 mod bundle + 新原版 bundle"""
    name: str
    old_paths: list[Path]
    new_paths: list[Path]


class LegacyRenameCase(NamedTuple):
    """legacy_rename 组案例：磁盘旧命名资源目录 + 新 bundle 文件"""
    name: str
    assets_dir: Path
    bundle_paths: list[Path]


class RessRegressCase(NamedTuple):
    """ress_regress 组案例：mod 文件 + 对应原文件"""
    name: str
    mod_path: Path
    original_path: Path


def _case_dirs(group_dir: Path) -> list[Path]:
    """列出组目录下所有案例子目录（按名称排序）"""
    if not group_dir.exists():
        return []
    return sorted(p for p in group_dir.iterdir() if p.is_dir())


def collect_sample_cases() -> list[SampleCase]:
    """扫描 sample 下所有案例：约定 <case>/assets 与 <case>/bundles 子目录"""
    cases: list[SampleCase] = []
    for case_dir in _case_dirs(SAMPLE_DIR):
        bundle_paths = find_all_files(case_dir / "bundles", ".bundle")
        if bundle_paths:
            cases.append(SampleCase(case_dir.name, case_dir / "assets", bundle_paths))
    return cases


def collect_update_cases() -> list[UpdateCase]:
    """扫描 mod_update 下所有案例：约定 <case>/old 与 <case>/new 子目录"""
    cases: list[UpdateCase] = []
    for case_dir in _case_dirs(MOD_UPDATE_DIR):
        old_paths = find_all_files(case_dir / "old", ".bundle")
        new_paths = find_all_files(case_dir / "new", ".bundle")
        if old_paths and new_paths:
            cases.append(UpdateCase(case_dir.name, old_paths, new_paths))
    return cases


def collect_legacy_rename_cases() -> list[LegacyRenameCase]:
    """扫描 legacy_rename 下所有案例：约定 <case>/assets 与 <case>/bundles 子目录"""
    cases: list[LegacyRenameCase] = []
    for case_dir in _case_dirs(LEGACY_RENAME_DIR):
        bundle_paths = find_all_files(case_dir / "bundles", ".bundle")
        if bundle_paths:
            cases.append(LegacyRenameCase(case_dir.name, case_dir / "assets", bundle_paths))
    return cases


def collect_ress_regress_cases() -> list[RessRegressCase]:
    """扫描 ress_regress 下所有案例：约定 <case>/mod 与 <case>/original 子目录，
    各取第一个文件；结构不完整的目录自动忽略。"""
    cases: list[RessRegressCase] = []
    for case_dir in _case_dirs(RESS_REGRESS_DIR):
        mods = find_all_files(case_dir / "mod", ".bundle")
        originals = find_all_files(case_dir / "original", ".bundle*")
        if mods and originals:
            cases.append(RessRegressCase(case_dir.name, mods[0], originals[0]))
    return cases


# 案例 fixture 名 → 收集函数，pytest_generate_tests 据此统一参数化
_CASE_COLLECTORS = {
    "sample_case": collect_sample_cases,
    "update_case": collect_update_cases,
    "legacy_rename_case": collect_legacy_rename_cases,
    "ress_regress_case": collect_ress_regress_cases,
}


def pytest_generate_tests(metafunc) -> None:
    """为引用案例 fixture 的测试按案例目录参数化；无数据时空参数集自动跳过"""
    for fixture_name, collect in _CASE_COLLECTORS.items():
        if fixture_name in metafunc.fixturenames:
            cases = collect()
            metafunc.parametrize(fixture_name, cases, ids=[c.name for c in cases])


def compare_images_mse(img1: Image.Image, img2: Image.Image) -> float:
    if img1.size != img2.size:
        raise ValueError(f"Size mismatch: {img1.size} vs {img2.size}")
    
    img1 = img1.convert("RGBA")
    img2 = img2.convert("RGBA")
    
    pixels1 = img1.load()
    pixels2 = img2.load()
    
    width, height = img1.size
    total_diff = 0.0
    
    for y in range(height):
        for x in range(width):
            p1 = pixels1[x, y]
            p2 = pixels2[x, y]
            for c in range(4):
                total_diff += (p1[c] - p2[c]) ** 2
    
    mse = total_diff / (width * height * 4)
    return mse


def find_first_file(directory: Path, extension: str) -> Path | None:
    if not directory.exists():
        return None
    files = list(directory.glob(f"*{extension}"))
    return files[0] if files else None


def find_all_files(directory: Path, extension: str) -> list[Path]:
    if not directory.exists():
        return []
    return list(directory.glob(f"*{extension}"))


def has_file(directory: Path, extension: str) -> bool:
    if not directory.exists():
        return False
    return bool(list(directory.glob(f"*{extension}")))


def compare_directory_assets(
    old_dir: Path,
    new_dir: Path,
    mse_threshold: float = 50.0,
) -> None:
    old_pngs = list(old_dir.glob("*.png"))
    new_pngs = list(new_dir.glob("*.png"))

    if old_pngs and new_pngs:
        for old_png in old_pngs:
            new_png = new_dir / old_png.name
            if new_png.exists():
                old_img = Image.open(old_png).convert("RGBA")
                new_img = Image.open(new_png).convert("RGBA")

                if old_img.size == new_img.size:
                    mse = compare_images_mse(old_img, new_img)
                    assert mse < mse_threshold, f"MSE={mse} >= {mse_threshold}"

    for ext in ("*.skel", "*.atlas"):
        old_files = list(old_dir.glob(ext))
        new_files = list(new_dir.glob(ext))
        if old_files and new_files:
            for old_file in old_files:
                new_file = new_dir / old_file.name
                if new_file.exists():
                    assert old_file.read_bytes() == new_file.read_bytes()


# ---------------------------------------------------------------------------
# 外部工具测试（SkelConverter / SpineViewerCLI）
#
# 工具路径解析约定：
#   1. 本地：编辑 tests/assets/external_tools/paths.toml（gitignore 覆盖），
#      填 exe 本体路径（与 GUI 设置一致）
#   2. CI：workflow 从 release 下载解压到 external_tools/converter、external_tools/viewer，
#      在约定目录两层以内按已知 exe 名查找，无需配置文件
#   3. 都没有 → None → 引用 fixture 的测试自动跳过
# ---------------------------------------------------------------------------

EXTERNAL_TOOLS_DIR = ASSETS_DIR / "external_tools"
PATHS_FILE = EXTERNAL_TOOLS_DIR / "paths.toml"

CONVERTER_EXE_NAMES = ("SpineSkeletonDataConverter.exe",)
VIEWER_EXE_NAMES = ("SpineViewerCLI.exe",)

# Spine 版本自举基准：游戏运行时 skel 为 4.2.x，本地编辑通常为 3.8.x
GAME_SPINE_VERSION = "4.2.33"
EDIT_SPINE_VERSION = "3.8.75"

# 渲染类测试开关：CI 软件渲染（llvmpipe）与 SFML 2.6 纹理回读不兼容（进程静默崩溃），
# workflow 中设置 SKIP_SPINE_RENDER=1 跳过渲染验证，渲染正确性由本地硬件 GL 环境验证；
# query / 版本转换不依赖渲染目标，不受影响
RENDER_SKIP_ENV = "SKIP_SPINE_RENDER"


def require_render_support() -> None:
    """渲染类测试入口：无渲染能力的环境自动跳过"""
    if os.environ.get(RENDER_SKIP_ENV) == "1":
        pytest.skip(f"{RENDER_SKIP_ENV}=1：无硬件 GL 环境，跳过渲染验证")


class SpineAssetSet(NamedTuple):
    """自举后的 Spine 三件套副本（skel/atlas/png 同名同目录）"""
    dir: Path
    skel_path: Path
    atlas_path: Path
    png_path: Path | None


def _find_exe_in_dir(directory: Path, exe_names: tuple[str, ...], max_depth: int) -> Path | None:
    """在目录内指定深度以内查找已知 exe 名（大小写不敏感）"""
    if not directory.is_dir():
        return None
    wanted = {name.lower() for name in exe_names}
    for exe in directory.rglob("*.exe"):
        if exe.name.lower() in wanted and len(exe.relative_to(directory).parts) <= max_depth:
            return exe
    return None


def resolve_external_tool(kind: str, exe_names: tuple[str, ...]) -> Path | None:
    """解析外部工具的 exe 路径；找不到返回 None（调用方据此跳过测试）"""
    # 1. paths.toml 配置（本地使用，填 exe 本体路径，与 GUI 设置一致）
    if PATHS_FILE.exists():
        try:
            data = tomllib.loads(PATHS_FILE.read_text(encoding="utf-8-sig"))
        except tomllib.TOMLDecodeError:
            data = {}
        configured = data.get(kind)
        if configured:
            path = Path(configured)
            return path if path.is_file() else None  # 已配置但无效，不回退到约定目录

    # 2. 无配置（CI 场景）：在约定子目录内查找
    return _find_exe_in_dir(EXTERNAL_TOOLS_DIR / kind, exe_names, max_depth=2)


@pytest.fixture(scope="session")
def spine_converter_path() -> Path:
    """SkelConverter exe 路径；未配置则跳过测试"""
    path = resolve_external_tool("converter", CONVERTER_EXE_NAMES)
    if path is None:
        pytest.skip("未找到 SkelConverter（本地编辑 paths.toml 或在 CI 设置 SKEL_CONVERTER_URL），跳过外部工具测试")
    return path


@pytest.fixture(scope="session")
def spine_viewer_path() -> Path:
    """SpineViewerCLI exe 路径；未配置则跳过测试"""
    path = resolve_external_tool("viewer", VIEWER_EXE_NAMES)
    if path is None:
        pytest.skip("未找到 SpineViewerCLI（本地编辑 paths.toml 或在 CI 设置 SPINE_VIEWER_URL），跳过外部工具测试")
    return path


def bootstrap_spine_assets(
    assets_dir: Path,
    target_version: str,
    converter_path: Path,
    output_dir: Path,
    log: LogFunc = no_log,
) -> SpineAssetSet | None:
    """将三件套自举到目标版本（副本操作，不改动原始 asset）。

    版本作为运行时属性现场自举：源 skel 已是目标版本（major.minor 一致）则直接复制；
    否则 SkelConverter 就地转换副本，降级到 3.x 时配套 atlas 降级（png 不变）。
    素材缺少 skel/atlas、版本探测失败或转换失败时返回 None（调用方跳过测试）。
    """
    if not assets_dir.is_dir():
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    for f in assets_dir.iterdir():
        if f.is_file():
            shutil.copy2(f, output_dir / f.name)

    skel_path = find_first_file(output_dir, ".skel")
    atlas_path = find_first_file(output_dir, ".atlas")
    if skel_path is None or atlas_path is None:
        return None

    current = get_skel_version(skel_path, log)
    if current is None:
        return None

    major_minor = ".".join(target_version.split(".")[:2])
    if not current.startswith(major_minor):
        if not SkelConverter.run(
            skel_path, converter_path=converter_path, target_version=target_version, log=log
        ):
            return None
        # 3.x skel 只能配 spine3 atlas，降级必须配套 atlas_downgrade
        if major_minor == "3.8" and not atlas_downgrade(atlas_path, output_dir, log=log):
            return None

    return SpineAssetSet(output_dir, skel_path, atlas_path, find_first_file(output_dir, ".png"))
