"""CRC scan and repair workers can be verified without opening a Tk window."""

import binascii
from types import SimpleNamespace

import pytest

from ba_modding_toolkit.gui.windows import abnormal_check_dialog as checks


@pytest.fixture
def worker(monkeypatch):
    messages = []
    monkeypatch.setattr(checks, "t", lambda key, **params: key)
    app = SimpleNamespace(char_map=None, logger=SimpleNamespace(log=messages.append),
                          get_extra_bytes=lambda: None)
    dialog = SimpleNamespace(app=app, _mismatch_items=[], should_stop=lambda: False,
                             after=lambda delay, callback: callback(),
                             _update_progress=lambda *args, **kwargs: None)
    return dialog, messages


def sample(tmp_path, payload, expected):
    path = tmp_path / f"assets-_mx-spinecharacters-fixture_spr-2026-10-25_001_assets_all_{expected}.bundle"
    path.write_bytes(payload)
    return path


def scan(dialog, monkeypatch, paths):
    items = [SimpleNamespace(path=path, parsed_name=None) for path in paths]
    monkeypatch.setattr(checks, "list_bundle_files", lambda directory: items)
    monkeypatch.setattr(checks, "analyze_trailing", lambda item: None)
    checks.AbnormalCheckDialog._scan_files(dialog, paths[0].parent)


def test_matching_file_is_not_reported(worker, monkeypatch, tmp_path):
    payload = b"matching synthetic file"
    expected = binascii.crc32(payload) & 0xFFFFFFFF
    path = sample(tmp_path, payload, expected)
    dialog, _ = worker
    scan(dialog, monkeypatch, [path])
    assert dialog._mismatch_items == []
    assert path.read_bytes() == payload


@pytest.mark.parametrize("expected", [0, 0x12345678])
def test_mismatch_records_actual_integer_crc(worker, monkeypatch, tmp_path, expected):
    payload = b"synthetic file with a different checksum"
    actual = binascii.crc32(payload) & 0xFFFFFFFF
    assert actual != expected
    path = sample(tmp_path, payload, expected)
    dialog, _ = worker
    scan(dialog, monkeypatch, [path])
    assert len(dialog._mismatch_items) == 1
    item = dialog._mismatch_items[0]
    assert item.path == path
    assert item.target_crc == expected
    assert item.actual_crc == actual
    assert isinstance(item.actual_crc, int)
    assert path.read_bytes() == payload


def test_unreadable_file_is_skipped_without_stopping_scan(worker, monkeypatch, tmp_path):
    missing = sample(tmp_path, b"removed", 0)
    missing.unlink()
    readable = sample(tmp_path, b"readable", 1)
    dialog, _ = worker
    scan(dialog, monkeypatch, [missing, readable])
    assert [item.path for item in dialog._mismatch_items] == [readable]


def test_repaired_file_is_verified_from_its_bytes(worker, tmp_path):
    payload = b"synthetic file to repair"
    expected = 0x12345678
    path = sample(tmp_path, payload, expected)
    dialog, messages = worker
    dialog._mismatch_items = [checks.MismatchItem(path, path.name, None, expected,
                                                  binascii.crc32(payload) & 0xFFFFFFFF)]
    checks.AbnormalCheckDialog._fix_files(dialog)
    assert binascii.crc32(path.read_bytes()) & 0xFFFFFFFF == expected
    assert "log.abnormal_check.fix_success" in messages
    assert "log.abnormal_check.fix_verify_failed" not in messages


def test_repair_returning_success_still_requires_matching_bytes(worker, monkeypatch, tmp_path):
    payload = b"unchanged synthetic file"
    expected = 0x12345678
    path = sample(tmp_path, payload, expected)
    dialog, messages = worker
    dialog._mismatch_items = [checks.MismatchItem(path, path.name, None, expected,
                                                  binascii.crc32(payload) & 0xFFFFFFFF)]
    monkeypatch.setattr(checks, "manipulate_file_crc", lambda *args: True)
    checks.AbnormalCheckDialog._fix_files(dialog)
    assert "log.abnormal_check.fix_verify_failed" in messages
    assert "log.abnormal_check.fix_success" not in messages
    assert path.read_bytes() == payload
