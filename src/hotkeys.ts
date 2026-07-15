import type { HotkeyEntry } from "./types";

const MODIFIER_CODES = new Set([
  "ControlLeft",
  "ControlRight",
  "ShiftLeft",
  "ShiftRight",
  "AltLeft",
  "AltRight",
  "MetaLeft",
  "MetaRight",
]);

const CODE_NAMES: Record<string, string> = {
  Enter: "ENTER",
  NumpadEnter: "NUMPAD_ENTER",
  Escape: "ESCAPE",
  Backspace: "BACKSPACE",
  Delete: "DELETE",
  Tab: "TAB",
  Space: "SPACE",
  Home: "HOME",
  End: "END",
  PageUp: "PAGE_UP",
  PageDown: "PAGE_DOWN",
  ArrowUp: "UP",
  ArrowDown: "DOWN",
  ArrowLeft: "LEFT",
  ArrowRight: "RIGHT",
  Insert: "INSERT",
  BracketLeft: "LEFT_BRACKET",
  BracketRight: "RIGHT_BRACKET",
  Slash: "SLASH",
  Backslash: "BACKSLASH",
  Comma: "COMMA",
  Period: "PERIOD",
  Minus: "MINUS",
  Equal: "EQUALS",
  NumpadAdd: "NUMPAD_PLUS",
  NumpadSubtract: "NUMPAD_MINUS",
  NumpadMultiply: "NUMPAD_MULTIPLY",
  NumpadDivide: "NUMPAD_DIVIDE",
  NumpadDecimal: "NUMPAD_DECIMAL",
};

export function eventToSpineHotkey(event: KeyboardEvent): string | null {
  if (MODIFIER_CODES.has(event.code)) return null;

  let base = CODE_NAMES[event.code];
  if (!base && /^Key[A-Z]$/.test(event.code)) base = event.code.slice(3);
  if (!base && /^Digit[0-9]$/.test(event.code)) base = event.code.slice(5);
  if (!base && /^F([1-9]|1[0-9]|2[0-4])$/.test(event.code)) base = event.code;
  if (!base && /^Numpad[0-9]$/.test(event.code)) base = `NUMPAD_${event.code.slice(6)}`;
  if (!base && event.code === "Semicolon") base = event.shiftKey ? "':'" : "';'";
  if (!base && event.code === "Quote") base = event.shiftKey ? "'\"'" : "'''";
  if (!base && event.code === "Backquote") base = event.shiftKey ? "'~'" : "'`'";
  if (!base) return "";

  const modifiers: string[] = [];
  if (event.ctrlKey) modifiers.push("ctrl");
  if (event.shiftKey) modifiers.push("shift");
  if (event.altKey) modifiers.push("alt");
  return [...modifiers, base].join(" + ");
}

export function cleanHotkey(value: string): string {
  return value
    .trim()
    .split("+")
    .map((part) => part.trim())
    .filter(Boolean)
    .join(" + ");
}

export function normalizeHotkey(value: string): string {
  const parts = cleanHotkey(value)
    .split(" + ")
    .filter(Boolean)
    .map((part) => {
      const lower = part.toLocaleLowerCase();
      return lower.length >= 3 && lower.startsWith("'") && lower.endsWith("'")
        ? lower.slice(1, -1)
        : lower;
    });
  const modifiers = ["ctrl", "shift", "alt"].filter((modifier) => parts.includes(modifier));
  const keys = parts.filter((part) => !["ctrl", "shift", "alt"].includes(part));
  return [...modifiers, ...keys].join("+");
}

export function findConflicts(entries: HotkeyEntry[]): Map<string, string[]> {
  const grouped = new Map<string, string[]>();
  entries.forEach((entry) => {
    const normalized = normalizeHotkey(entry.value);
    if (!normalized) return;
    grouped.set(normalized, [...(grouped.get(normalized) ?? []), entry.entryId]);
  });
  return new Map([...grouped].filter(([, ids]) => ids.length > 1));
}

export function bindingRecord(entries: HotkeyEntry[]): Record<string, string> {
  return Object.fromEntries(entries.map((entry) => [entry.entryId, entry.value]));
}
