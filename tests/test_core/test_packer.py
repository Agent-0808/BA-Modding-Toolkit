import pytest
import re
from pathlib import Path
from PIL import Image
import shutil

from ba_modding_toolkit.core import (
    process_asset_packing,
    process_asset_extraction,
    SaveOptions,
)
from ba_modding_toolkit.bundle import Bundle
from ba_modding_toolkit.models import NameTypeKey, AssetType
from conftest import (
    compare_images_mse,
    has_sample_bundle, has_sample_image, has_sample_skel, has_sample_atlas,
    has_spine_legacy_samples,
)

MSE_THRESHOLD = 20.0


@pytest.mark.skipif(
    not all([has_sample_bundle(), has_sample_image(), has_sample_skel(), has_sample_atlas()]),
    reason="sample.bundle, sample.png, sample.skel, sample.atlas ARE REQUIRED"
)
class TestAssetPacking:
    def test_pack_with_bleed(
        self,
        sample_bundle_path: Path,
        sample_image_path: Path,
        tmp_path: Path,
    ):
        asset_folder = tmp_path / "assets"
        asset_folder.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        shutil.copy(sample_image_path, asset_folder / sample_image_path.name)
        
        original_img = Image.open(sample_image_path).convert("RGBA")
        original_size = original_img.size
        
        save_options = SaveOptions(
            perform_crc=False,
            compression="none",
        )
        
        success, msg, _ = process_asset_packing(
            target_bundle_path=sample_bundle_path,
            assets=asset_folder,
            output_dir=output_dir,
            save_options=save_options,
            enable_bleed=True
        )
        
        assert success is True, msg
        
        packed_bundle = output_dir / sample_bundle_path.name
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        
        process_asset_extraction(
            bundle_path=packed_bundle,
            output_dir=extract_dir,
            asset_types_to_extract={"Texture2D"}
        )
        
        extracted_png = extract_dir / sample_image_path.name
        if extracted_png.exists():
            extracted_img = Image.open(extracted_png)
            assert extracted_img.size == original_size

    def test_pack_textasset(
        self,
        sample_bundle_path: Path,
        sample_skel_path: Path,
        sample_atlas_path: Path,
        tmp_path: Path,
    ):
        asset_folder = tmp_path / "assets"
        asset_folder.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        shutil.copy(sample_skel_path, asset_folder / sample_skel_path.name)
        shutil.copy(sample_atlas_path, asset_folder / sample_atlas_path.name)
        
        original_skel_content = sample_skel_path.read_bytes()
        original_atlas_content = sample_atlas_path.read_bytes()
        
        save_options = SaveOptions(
            perform_crc=False,
            compression="none",
        )
        
        success, msg, _ = process_asset_packing(
            target_bundle_path=sample_bundle_path,
            assets=asset_folder,
            output_dir=output_dir,
            save_options=save_options
        )
        assert success is True, msg
        
        packed_bundle = output_dir / sample_bundle_path.name
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        
        success, msg = process_asset_extraction(
            bundle_path=packed_bundle,
            output_dir=extract_dir,
            asset_types_to_extract={"TextAsset", "Texture2D"}
        )
        
        assert success is True, msg
        
        extracted_skel = extract_dir / sample_skel_path.name
        assert extracted_skel.exists()
        extracted_skel_content = extracted_skel.read_bytes()
        assert extracted_skel_content == original_skel_content
        
        extracted_atlas = extract_dir / sample_atlas_path.name
        assert extracted_atlas.exists()
        extracted_atlas_content = extracted_atlas.read_bytes()
        assert extracted_atlas_content == original_atlas_content

    def test_pack_and_extract_roundtrip(
        self,
        sample_bundle_path: Path,
        sample_image_path: Path,
        sample_skel_path: Path,
        sample_atlas_path: Path,
        tmp_path: Path,
    ):
        asset_folder = tmp_path / "assets"
        asset_folder.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        
        shutil.copy(sample_image_path, asset_folder / sample_image_path.name)
        shutil.copy(sample_skel_path, asset_folder / sample_skel_path.name)
        shutil.copy(sample_atlas_path, asset_folder / sample_atlas_path.name)
        
        original_img = Image.open(sample_image_path).convert("RGBA")
        original_skel_content = sample_skel_path.read_bytes()
        original_atlas_content = sample_atlas_path.read_bytes()
        
        save_options = SaveOptions(
            perform_crc=False,
            compression="none",
        )
        
        success, msg, _ = process_asset_packing(
            target_bundle_path=sample_bundle_path,
            assets=asset_folder,
            output_dir=output_dir,
            save_options=save_options
        )
        
        assert success is True, msg
        
        packed_bundle = output_dir / sample_bundle_path.name
        assert packed_bundle.exists()
        
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        
        success, msg = process_asset_extraction(
            bundle_path=packed_bundle,
            output_dir=extract_dir,
            asset_types_to_extract={"Texture2D", "TextAsset"}
        )
        
        assert success is True, msg
        
        extracted_png = extract_dir / sample_image_path.name
        assert extracted_png.exists()
        
        extracted_img = Image.open(extracted_png).convert("RGBA")
        
        mse = compare_images_mse(original_img, extracted_img)
        assert mse < MSE_THRESHOLD, f"MSE={mse} >= {MSE_THRESHOLD}"

        extracted_skel = extract_dir / sample_skel_path.name
        assert extracted_skel.exists()
        extracted_skel_content = extracted_skel.read_bytes()
        assert extracted_skel_content == original_skel_content

        extracted_atlas = extract_dir / sample_atlas_path.name
        assert extracted_atlas.exists()
        extracted_atlas_content = extracted_atlas.read_bytes()
        assert extracted_atlas_content == original_atlas_content


@pytest.mark.skipif(
    not has_spine_legacy_samples(),
    reason="spine/old_assets/ and spine/new_bundle/ ARE REQUIRED"
)
class TestLegacyRenameAssetPacking:
    """测试旧版文件名修正 + Asset Packing 的完整流程
    """

    def test_pack_assets_with_rename(
        self,
        spine_old_assets_dir: Path,
        spine_new_bundle_path: Path,
        tmp_path: Path,
    ):
        """旧版资产通过 enable_rename_fix 打包到新版 Bundle"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        save_options = SaveOptions(perform_crc=False, compression="none")

        success, msg, _ = process_asset_packing(
            target_bundle_path=spine_new_bundle_path,
            assets=spine_old_assets_dir,
            output_dir=output_dir,
            save_options=save_options,
            enable_rename_fix=True,
        )

        assert success is True, msg

        # 验证输出 bundle 存在
        packed_bundles = list(output_dir.glob("*.bundle"))
        assert len(packed_bundles) >= 1

        # 从打包后的 bundle 中提取资源，验证 PNG 名称已正确替换
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        process_asset_extraction(
            bundle_path=packed_bundles[0],
            output_dir=extract_dir,
            asset_types_to_extract={"Texture2D", "TextAsset"},
        )

        # 获取 Bundle 中期望的 Texture2D 名称
        bundle = Bundle.load(packed_bundles[0])
        expected_png_stems: set[str] = set()
        for key in bundle.get_asset_keys(asset_types={AssetType.Texture2D}):
            if isinstance(key, NameTypeKey) and key.name:
                expected_png_stems.add(key.name)

        # 提取出的 PNG 文件名应匹配 Bundle 中的名称
        extracted_pngs = list(extract_dir.glob("*.png"))
        extracted_stems = {p.stem for p in extracted_pngs}
        for stem in expected_png_stems:
            assert stem in extracted_stems, f"期望 {stem}.png 存在于提取结果中"

    def test_pack_assets_rename_no_png_match(
        self,
        spine_old_assets_dir: Path,
        spine_new_bundle_path: Path,
        tmp_path: Path,
    ):
        """不启用 rename_fix 时，旧版 PNG 无法匹配 Bundle 中的 Texture2D"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        save_options = SaveOptions(perform_crc=False, compression="none")

        success, msg, file_pairs = process_asset_packing(
            target_bundle_path=spine_new_bundle_path,
            assets=spine_old_assets_dir,
            output_dir=output_dir,
            save_options=save_options,
            enable_rename_fix=False,
        )

        # atlas/skel 名称匹配所以 packing 成功
        assert success is True, msg

        # 但提取打包后的 bundle，PNG 数据应与原始 bundle 相同（未被替换）
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        process_asset_extraction(
            bundle_path=file_pairs[0].output,
            output_dir=extract_dir,
            asset_types_to_extract={"Texture2D"},
        )

        # 从原始 bundle 提取 PNG 作对比
        original_extract_dir = tmp_path / "original"
        original_extract_dir.mkdir()
        process_asset_extraction(
            bundle_path=spine_new_bundle_path,
            output_dir=original_extract_dir,
            asset_types_to_extract={"Texture2D"},
        )

        # 打包后的 PNG 数据应与原始 bundle 的 PNG 数据一致（未被替换）
        for orig_png in original_extract_dir.glob("*.png"):
            packed_png = extract_dir / orig_png.name
            if packed_png.exists():
                assert orig_png.read_bytes() == packed_png.read_bytes(), \
                    f"不启用 rename_fix 时 {orig_png.name} 不应被替换"

    def test_atlas_references_correct_after_pack(
        self,
        spine_old_assets_dir: Path,
        spine_new_bundle_path: Path,
        tmp_path: Path,
    ):
        """打包后提取的 atlas 中不应包含旧版 PNG 引用"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        save_options = SaveOptions(perform_crc=False, compression="none")

        success, msg, _ = process_asset_packing(
            target_bundle_path=spine_new_bundle_path,
            assets=spine_old_assets_dir,
            output_dir=output_dir,
            save_options=save_options,
            enable_rename_fix=True,
        )

        assert success is True, msg

        packed_bundles = list(output_dir.glob("*.bundle"))
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        process_asset_extraction(
            bundle_path=packed_bundles[0],
            output_dir=extract_dir,
            asset_types_to_extract={"TextAsset"},
        )

        for atlas_file in extract_dir.glob("*.atlas"):
            content = atlas_file.read_text(encoding='utf-8')
            # 检测旧版格式：数字直接跟在非下划线字符后
            old_refs = re.findall(r'\w+\d+\.png', content)
            for ref in old_refs:
                stem = ref.replace('.png', '')
                if re.search(r'[^_]\d+$', stem):
                    pytest.fail(f"Atlas 中仍包含旧版 PNG 引用: {ref}")