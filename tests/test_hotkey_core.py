import json
import tempfile
import unittest
from pathlib import Path

from hotkey_core import (
    HotkeyDocument,
    apply_preset,
    find_conflicts,
    load_preset,
    normalize_hotkey,
    save_preset,
)


SAMPLE = (
    "--- General ---\r\n"
    "Undo: ctrl + Z\r\n"
    "Redo: ctrl + Y\r\n"
    "Redo: ctrl + shift + Z\r\n"
    "--- General ---\r\n"
    "Next Skin: PERIOD\r\n"
    "--- Playback ---\r\n"
    "Next Key: 'W'\r\n"
    "Previous Key: \r\n"
)


class HotkeyDocumentTests(unittest.TestCase):
    def test_round_trip_preserves_crlf_and_duplicate_identifiers(self):
        document = HotkeyDocument.from_text(SAMPLE)
        self.assertEqual(document.render(), SAMPLE)
        self.assertEqual(len(document.entries), 6)
        self.assertNotEqual(document.entries[1].entry_id, document.entries[2].entry_id)
        self.assertEqual(document.entries[3].group_label, "General (2)")

    def test_edit_only_changes_selected_line(self):
        document = HotkeyDocument.from_text(SAMPLE)
        target = document.entries[-1]
        document.set_value(target.entry_id, "shift+F")
        self.assertIn("Previous Key: shift + F\r\n", document.render())
        self.assertTrue(document.dirty)
        document.reset_value(target.entry_id)
        self.assertFalse(document.dirty)

    def test_conflict_normalizes_quoted_character(self):
        document = HotkeyDocument.from_text("--- A ---\nOne: W\nTwo: 'w'\n")
        conflicts = find_conflicts(document.entries)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(normalize_hotkey("ctrl+shift+'W'"), "ctrl+shift+w")

    def test_preset_save_load_and_apply(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            document = HotkeyDocument.from_text(SAMPLE)
            document.set_value(document.entries[0].entry_id, "alt + Z")
            preset_path = save_preset(temp_dir, "Bộ test", document)
            payload = load_preset(preset_path)
            self.assertEqual(payload["name"], "Bộ test")

            fresh = HotkeyDocument.from_text(SAMPLE)
            matched, missing = apply_preset(fresh, payload)
            self.assertEqual((matched, missing), (6, 0))
            self.assertEqual(fresh.entries[0].value, "alt + Z")

    def test_atomic_save_creates_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "hotkeys.txt"
            source.write_bytes(SAMPLE.encode("utf-8"))
            document = HotkeyDocument.load(source)
            document.set_value(document.entries[0].entry_id, "alt + U")
            backup = document.save_atomic(root / "backups")
            self.assertTrue(backup.exists())
            self.assertEqual(backup.read_bytes(), SAMPLE.encode("utf-8"))
            self.assertIn(b"Undo: alt + U\r\n", source.read_bytes())
            self.assertFalse(document.dirty)

    def test_invalid_preset_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad.json"
            path.write_text(json.dumps({"format_version": 999, "bindings": {}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_preset(path)


if __name__ == "__main__":
    unittest.main()

