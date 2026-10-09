import pytest
from pathlib import Path
from typing import NamedTuple
from PIL import Image

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
