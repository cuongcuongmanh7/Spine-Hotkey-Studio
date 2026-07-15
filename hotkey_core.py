from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


SECTION_RE = re.compile(r"^---\s+(.+?)\s+---$")
PRESET_VERSION = 1


@dataclass
class HotkeyEntry:
    entry_id: str
    section: str
    section_occurrence: int
    action: str
    action_occurrence: int
    value: str
    original_value: str
    line_index: int

    @property
    def group_label(self) -> str:
        return self.section if self.section_occurrence == 1 else f"{self.section} ({self.section_occurrence})"


class HotkeyDocument:
    def __init__(
        self,
        path: Path,
        lines: list[str],
        newline: str,
        trailing_newline: bool,
        entries: list[HotkeyEntry],
        source_mtime_ns: int | None,
    ) -> None:
        self.path = path
        self.lines = lines
        self.newline = newline
        self.trailing_newline = trailing_newline
        self.entries = entries
        self.source_mtime_ns = source_mtime_ns

    @classmethod
    def load(cls, path: str | Path) -> "HotkeyDocument":
        file_path = Path(path).resolve()
        raw = file_path.read_bytes()
        text = raw.decode("utf-8-sig")
        newline = "\r\n" if b"\r\n" in raw else "\n"
        trailing_newline = text.endswith(("\r\n", "\n"))
        lines = text.splitlines()
        entries = cls._parse_entries(lines)
        if not entries:
            raise ValueError("Không tìm thấy dòng hotkey hợp lệ trong file.")
        return cls(
            path=file_path,
            lines=lines,
            newline=newline,
            trailing_newline=trailing_newline,
            entries=entries,
            source_mtime_ns=file_path.stat().st_mtime_ns,
        )

    @classmethod
    def from_text(cls, text: str, path: str | Path = "hotkeys.txt") -> "HotkeyDocument":
        newline = "\r\n" if "\r\n" in text else "\n"
        lines = text.splitlines()
        return cls(
            path=Path(path),
            lines=lines,
            newline=newline,
            trailing_newline=text.endswith(("\r\n", "\n")),
            entries=cls._parse_entries(lines),
            source_mtime_ns=None,
        )

    @staticmethod
    def _parse_entries(lines: list[str]) -> list[HotkeyEntry]:
        entries: list[HotkeyEntry] = []
        section = "Khác"
        section_occurrence = 0
        section_counts: dict[str, int] = {}
        action_counts: dict[tuple[str, int, str], int] = {}

        for line_index, line in enumerate(lines):
            section_match = SECTION_RE.match(line)
            if section_match:
                section = section_match.group(1).strip()
                section_counts[section] = section_counts.get(section, 0) + 1
                section_occurrence = section_counts[section]
                continue

            if ":" not in line or line.startswith("---"):
                continue
            action, value = line.split(":", 1)
            action = action.strip()
            if not action:
                continue
            value = value.strip()
            action_key = (section, section_occurrence, action)
            action_counts[action_key] = action_counts.get(action_key, 0) + 1
            action_occurrence = action_counts[action_key]
            entry_id = make_entry_id(section, section_occurrence, action, action_occurrence)
            entries.append(
                HotkeyEntry(
                    entry_id=entry_id,
                    section=section,
                    section_occurrence=section_occurrence,
                    action=action,
                    action_occurrence=action_occurrence,
                    value=value,
                    original_value=value,
                    line_index=line_index,
                )
            )
        return entries

    @property
    def dirty(self) -> bool:
        return any(entry.value != entry.original_value for entry in self.entries)

    @property
    def structure_fingerprint(self) -> str:
        structure = "\n".join(entry.entry_id for entry in self.entries)
        return hashlib.sha256(structure.encode("utf-8")).hexdigest()[:16]

    def get(self, entry_id: str) -> HotkeyEntry | None:
        return next((entry for entry in self.entries if entry.entry_id == entry_id), None)

    def set_value(self, entry_id: str, value: str) -> bool:
        entry = self.get(entry_id)
        if entry is None:
            return False
        entry.value = clean_hotkey(value)
        return True

    def reset_value(self, entry_id: str) -> bool:
        entry = self.get(entry_id)
        if entry is None:
            return False
        entry.value = entry.original_value
        return True

    def reset_all(self) -> None:
        for entry in self.entries:
            entry.value = entry.original_value

    def render(self) -> str:
        rendered = list(self.lines)
        for entry in self.entries:
            original_line = rendered[entry.line_index]
            prefix = original_line.split(":", 1)[0].rstrip()
            rendered[entry.line_index] = f"{prefix}: {entry.value}"
        text = self.newline.join(rendered)
        if self.trailing_newline:
            text += self.newline
        return text

    def changed_on_disk(self) -> bool:
        if self.source_mtime_ns is None or not self.path.exists():
            return False
        return self.path.stat().st_mtime_ns != self.source_mtime_ns

    def save_atomic(self, backup_dir: str | Path) -> Path:
        backup_path = create_backup(self.path, backup_dir)
        output = self.render().encode("utf-8")
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent, delete=False
            ) as temp_file:
                temp_file.write(output)
                temp_file.flush()
                os.fsync(temp_file.fileno())
                temp_name = temp_file.name
            os.replace(temp_name, self.path)
        finally:
            if temp_name and Path(temp_name).exists():
                Path(temp_name).unlink(missing_ok=True)

        stat = self.path.stat()
        self.source_mtime_ns = stat.st_mtime_ns
        self.lines = self.render().splitlines()
        for entry in self.entries:
            entry.original_value = entry.value
        return backup_path


def make_entry_id(section: str, section_occurrence: int, action: str, action_occurrence: int) -> str:
    return f"{section}\x1f{section_occurrence}\x1f{action}\x1f{action_occurrence}"


def clean_hotkey(value: str) -> str:
    return re.sub(r"\s*\+\s*", " + ", value.strip())


def normalize_hotkey(value: str) -> str:
    value = clean_hotkey(value)
    if not value:
        return ""
    parts = [part.strip() for part in value.split(" + ")]
    normalized: list[str] = []
    for part in parts:
        lowered = part.lower()
        if len(lowered) >= 3 and lowered.startswith("'") and lowered.endswith("'"):
            lowered = lowered[1:-1]
        normalized.append(lowered)
    modifiers = [item for item in ("ctrl", "shift", "alt") if item in normalized]
    keys = [item for item in normalized if item not in {"ctrl", "shift", "alt"}]
    return "+".join(modifiers + keys)


def find_conflicts(entries: Iterable[HotkeyEntry]) -> dict[str, list[str]]:
    by_hotkey: dict[str, list[str]] = {}
    for entry in entries:
        normalized = normalize_hotkey(entry.value)
        if normalized:
            by_hotkey.setdefault(normalized, []).append(entry.entry_id)
    return {hotkey: ids for hotkey, ids in by_hotkey.items() if len(ids) > 1}


def create_backup(source_path: str | Path, backup_dir: str | Path) -> Path:
    source = Path(source_path)
    destination_dir = Path(backup_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = destination_dir / f"{source.stem}-{timestamp}{source.suffix}.bak"
    shutil.copy2(source, destination)
    return destination


def preset_payload(name: str, document: HotkeyDocument) -> dict:
    return {
        "format_version": PRESET_VERSION,
        "name": name.strip(),
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_file": document.path.name,
        "structure_fingerprint": document.structure_fingerprint,
        "bindings": {entry.entry_id: entry.value for entry in document.entries},
    }


def safe_preset_filename(name: str) -> str:
    cleaned = re.sub(r"[^\w\-. ]+", "", name.strip(), flags=re.UNICODE)
    cleaned = re.sub(r"\s+", "-", cleaned).strip(".-_")
    return (cleaned or "preset")[:80] + ".json"


def save_preset(directory: str | Path, name: str, document: HotkeyDocument, overwrite: bool = False) -> Path:
    if not name.strip():
        raise ValueError("Tên preset không được để trống.")
    preset_dir = Path(directory)
    preset_dir.mkdir(parents=True, exist_ok=True)
    path = preset_dir / safe_preset_filename(name)
    if path.exists() and not overwrite:
        raise FileExistsError(f"Preset '{name}' đã tồn tại.")
    path.write_text(json.dumps(preset_payload(name, document), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_preset(path: str | Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("format_version") != PRESET_VERSION or not isinstance(payload.get("bindings"), dict):
        raise ValueError("Định dạng preset không được hỗ trợ.")
    return payload


def apply_preset(document: HotkeyDocument, payload: dict) -> tuple[int, int]:
    bindings = payload.get("bindings", {})
    matched = 0
    for entry in document.entries:
        if entry.entry_id in bindings:
            entry.value = clean_hotkey(str(bindings[entry.entry_id]))
            matched += 1
    missing = max(0, len(bindings) - matched)
    return matched, missing

