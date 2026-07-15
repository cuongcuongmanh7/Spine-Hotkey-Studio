import { describe, expect, it } from "vitest";
import { cleanHotkey, eventToSpineHotkey, normalizeHotkey, overrideConflict } from "./hotkeys";
import type { HotkeyEntry } from "./types";

function entry(entryId: string, value: string): HotkeyEntry {
  return {
    entryId,
    section: "Test",
    sectionOccurrence: 1,
    groupLabel: "Test",
    action: entryId,
    actionOccurrence: 1,
    value,
    originalValue: value,
    lineIndex: 0,
  };
}

function keyboardEvent(code: string, modifiers: Partial<KeyboardEvent> = {}): KeyboardEvent {
  return {
    code,
    ctrlKey: false,
    shiftKey: false,
    altKey: false,
    ...modifiers,
  } as KeyboardEvent;
}

describe("eventToSpineHotkey", () => {
  it("records a plain Q without a phantom Alt modifier", () => {
    expect(eventToSpineHotkey(keyboardEvent("KeyQ"))).toBe("Q");
  });

  it("records a real Alt modifier", () => {
    expect(eventToSpineHotkey(keyboardEvent("KeyQ", { altKey: true }))).toBe("alt + Q");
  });

  it("keeps Spine punctuation syntax", () => {
    expect(eventToSpineHotkey(keyboardEvent("Semicolon"))).toBe("';'");
    expect(eventToSpineHotkey(keyboardEvent("Quote", { shiftKey: true }))).toBe("shift + '\"'");
  });
});

describe("hotkey normalization", () => {
  it("normalizes spacing", () => {
    expect(cleanHotkey("ctrl+ shift +Q")).toBe("ctrl + shift + Q");
  });

  it("treats quoted and unquoted letter bindings as the same key", () => {
    expect(normalizeHotkey("'W'")).toBe(normalizeHotkey("W"));
  });
});

describe("overrideConflict", () => {
  it("giữ lệnh được ưu tiên và xóa mọi lệnh trùng", () => {
    const entries = [
      entry("one", "ctrl + Q"),
      entry("two", "CTRL+Q"),
      entry("three", "ctrl + W"),
      entry("four", "ctrl + q"),
    ];

    expect(overrideConflict(entries, "two")).toEqual(["one", "four"]);
    expect(entries.map((item) => item.value)).toEqual(["", "CTRL+Q", "ctrl + W", ""]);
  });
});
