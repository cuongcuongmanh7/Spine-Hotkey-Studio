import { describe, expect, it } from "vitest";
import { cleanHotkey, eventToSpineHotkey, normalizeHotkey } from "./hotkeys";

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
