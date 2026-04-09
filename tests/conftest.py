import pytest
from pathlib import Path
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


@pytest.fixture
def sample_bundle_path() -> Path | None:
    return find_first_file(PACKER_DIR, ".bundle")


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
def old_mod_bundle_path() -> Path | None:
    return find_first_file(MOD_UPDATE_OLD_DIR, ".bundle")


@pytest.fixture
def new_original_bundle_path() -> Path | None:
    return find_first_file(MOD_UPDATE_NEW_DIR, ".bundle")


@pytest.fixture
def legacy_bundle_path() -> Path | None:
    return find_first_file(LEGACY_FORMAT_LEGACY_DIR, ".bundle")


@pytest.fixture
def modern_dir_path() -> Path:
    return LEGACY_FORMAT_MODERN_DIR
