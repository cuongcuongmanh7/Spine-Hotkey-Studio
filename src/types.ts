export interface HotkeyEntry {
  entryId: string;
  section: string;
  sectionOccurrence: number;
  groupLabel: string;
  action: string;
  actionOccurrence: number;
  value: string;
  originalValue: string;
  lineIndex: number;
}

export interface HotkeySnapshot {
  path: string;
  sourceToken: string;
  structureFingerprint: string;
  entries: HotkeyEntry[];
}

export interface SaveHotkeysResult {
  sourceToken: string;
  backupPath: string;
  updatedCount: number;
}

export interface PresetPayload {
  formatVersion: number;
  name: string;
  createdAt: string;
  sourceFile: string;
  structureFingerprint: string;
  bindings: Record<string, string>;
}

export interface PresetSummary {
  fileName: string;
  name: string;
  createdAt: string;
  bindingCount: number;
}
