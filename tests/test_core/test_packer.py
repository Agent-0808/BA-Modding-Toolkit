import pytest
from pathlib import Path
from PIL import Image
import shutil

from ba_modding_toolkit.core import (
    process_asset_packing,
    process_asset_extraction,
    SaveOptions,
)
from conftest import compare_images_mse, has_sample_bundle, has_sample_image, has_sample_skel, has_sample_atlas

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
            asset_folder=asset_folder,
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
            asset_folder=asset_folder,
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
            asset_folder=asset_folder,
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