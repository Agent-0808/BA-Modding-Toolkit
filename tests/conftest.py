import pytest
from pathlib import Path
from typing import NamedTuple
from PIL import Image

ASSETS_DIR = Path(__file__).parent / "assets"
BUNDLES_DIR = ASSETS_DIR / "bundles"
PACKER_DIR = ASSETS_DIR / "packer"

MOD_UPDATE_DIR = ASSETS_DIR / "mod_update"
MOD_UPDATE_OLD_DIR = MOD_UPDATE_DIR / "old"
MOD_UPDATE_NEW_DIR = MOD_UPDATE_DIR / "new"

LEGACY_FORMAT_DIR = ASSETS_DIR / "legacy_format"
LEGACY_FORMAT_LEGACY_DIR = LEGACY_FORMAT_DIR / "legacy"
LEGACY_FORMAT_MODERN_DIR = LEGACY_FORMAT_DIR / "modern"

SPINE_DIR = ASSETS_DIR / "spine"
SPINE_OLD_ASSETS_DIR = SPINE_DIR / "old_assets"
SPINE_NEW_BUNDLE_DIR = SPINE_DIR / "new_bundle"

# .resS/.resource 流引用回归测试数据：每个案例一个文件夹，内含 mod/ 与 original/ 子目录
RESS_REGRESS_DIR = ASSETS_DIR / "ress_regress"


class RessRegressCase(NamedTuple):
    """一组 ress 回归测试案例：mod 文件 + 对应原文件"""
    name: str
    mod_path: Path
    original_path: Path


def collect_ress_regress_cases() -> list[RessRegressCase]:
    """扫描 ress_regress 下所有案例目录，自动发现 mod/original 文件对。

    目录约定：<case>/mod/*.bundle 与 <case>/original/*.bundle(.backup)，
    各取第一个文件；结构不完整的目录自动忽略。
    """
    cases: list[RessRegressCase] = []
    if not RESS_REGRESS_DIR.exists():
        return cases
    for case_dir in sorted(p for p in RESS_REGRESS_DIR.iterdir() if p.is_dir()):
        mods = find_all_files(case_dir / "mod", ".bundle")
        originals = find_all_files(case_dir / "original", ".bundle*")
        if mods and originals:
            cases.append(RessRegressCase(case_dir.name, mods[0], originals[0]))
    return cases


def pytest_generate_tests(metafunc) -> None:
    """为引用 ress_regress_case fixture 的测试按案例目录参数化"""
    if "ress_regress_case" in metafunc.fixturenames:
        cases = collect_ress_regress_cases()
        metafunc.parametrize(
            "ress_regress_case",
            cases,
            ids=[c.name for c in cases],
        )


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

def file_list(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return list(directory.iterdir())


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


def has_sample_bundle() -> bool:
    return has_file(PACKER_DIR, ".bundle")


def has_sample_image() -> bool:
    return has_file(PACKER_DIR, ".png")


def has_sample_skel() -> bool:
    return has_file(PACKER_DIR, ".skel")


def has_sample_atlas() -> bool:
    return has_file(PACKER_DIR, ".atlas")


def has_mod_update_samples() -> bool:
    return has_file(MOD_UPDATE_OLD_DIR, ".bundle") and has_file(MOD_UPDATE_NEW_DIR, ".bundle")


def has_legacy_format_samples() -> bool:
    return has_file(LEGACY_FORMAT_LEGACY_DIR, ".bundle") and has_file(LEGACY_FORMAT_MODERN_DIR, ".bundle")


def has_spine_legacy_samples() -> bool:
    return has_file(SPINE_OLD_ASSETS_DIR, ".atlas") and has_file(SPINE_NEW_BUNDLE_DIR, ".bundle")


@pytest.fixture
def sample_bundle_paths() -> list[Path]:
    return find_all_files(PACKER_DIR, ".bundle")


@pytest.fixture
def sample_bundle_path(sample_bundle_paths: list[Path]) -> Path | None:
    """单文件 fixture，返回 sample_bundle_paths[0]"""
    return sample_bundle_paths[0] if sample_bundle_paths else None


@pytest.fixture
def sample_image_path() -> Path | None:
    return find_first_file(PACKER_DIR, ".png")


@pytest.fixture
def sample_skel_path() -> Path | None:
    return find_first_file(PACKER_DIR, ".skel")


@pytest.fixture
def sample_atlas_path() -> Path | None:
    return find_first_file(PACKER_DIR, ".atlas")


@pytest.fixture
def old_mod_bundle_paths() -> list[Path]:
    return find_all_files(MOD_UPDATE_OLD_DIR, ".bundle")


@pytest.fixture
def old_mod_bundle_path(old_mod_bundle_paths: list[Path]) -> Path | None:
    """单文件 fixture，返回 old_mod_bundle_paths[0]"""
    return old_mod_bundle_paths[0] if old_mod_bundle_paths else None


@pytest.fixture
def new_original_bundle_paths() -> list[Path]:
    return find_all_files(MOD_UPDATE_NEW_DIR, ".bundle")


@pytest.fixture
def new_original_bundle_path(new_original_bundle_paths: list[Path]) -> Path | None:
    """单文件 fixture，返回 new_original_bundle_paths[0]"""
    return new_original_bundle_paths[0] if new_original_bundle_paths else None


@pytest.fixture
def legacy_bundle_path() -> Path | None:
    return find_first_file(LEGACY_FORMAT_LEGACY_DIR, ".bundle")


@pytest.fixture
def modern_dir_path() -> Path:
    return LEGACY_FORMAT_MODERN_DIR


@pytest.fixture
def modern_bundles_path() -> list[Path]:
    if not LEGACY_FORMAT_MODERN_DIR.exists():
        return []
    return list(LEGACY_FORMAT_MODERN_DIR.glob("*.bundle"))


@pytest.fixture
def spine_old_assets_dir() -> Path:
    return SPINE_OLD_ASSETS_DIR


@pytest.fixture
def spine_new_bundle_dir() -> Path:
    return SPINE_NEW_BUNDLE_DIR


@pytest.fixture
def spine_new_bundle_path() -> list[Path]:
    return find_all_files(SPINE_NEW_BUNDLE_DIR, ".bundle")
