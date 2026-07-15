import { invoke } from "@tauri-apps/api/core";
import "./styles.css";
import { bindingRecord, cleanHotkey, eventToSpineHotkey, findConflicts, overrideConflict } from "./hotkeys";
import type {
  HotkeyEntry,
  HotkeySnapshot,
  PresetPayload,
  PresetSummary,
  SaveHotkeysResult,
} from "./types";

document.querySelector<HTMLDivElement>("#app")!.innerHTML = `
  <main class="app-shell">
    <header class="topbar">
      <div class="brand-block">
        <div class="brand-mark" aria-hidden="true">S</div>
        <div>
          <h1>Spine Hotkey Studio</h1>
          <p id="target-path" class="target-path">Đang kết nối hotkeys.txt…</p>
        </div>
      </div>
      <div class="topbar-actions">
        <button id="reload-button" class="button button-secondary" type="button">Tải lại</button>
        <button id="apply-button" class="button button-primary" type="button">Áp dụng vào Spine</button>
      </div>
    </header>

    <section class="workspace">
      <aside class="preset-panel surface">
        <div class="panel-heading">
          <span class="eyebrow">PRESET</span>
          <h2>Các bộ phím của bạn</h2>
        </div>
        <div id="preset-list" class="preset-list" role="list" aria-label="Danh sách preset">
          <div class="empty-state compact">Chưa có preset</div>
        </div>
        <p id="preset-meta" class="preset-meta">Chỉnh hotkey rồi lưu bộ đầu tiên.</p>
        <button id="save-preset-button" class="button button-secondary button-wide" type="button">Lưu preset <span class="button-shortcut">Ctrl S</span></button>
        <button id="save-as-preset-button" class="button button-ghost button-wide" type="button">Lưu thành preset mới…</button>
        <div class="preset-actions">
          <button id="duplicate-preset-button" class="button button-ghost" type="button">Sao chép</button>
        </div>
      </aside>

      <section class="hotkey-workspace">
        <div class="filterbar">
          <label class="search-field control-rounded">
            <span class="search-icon" aria-hidden="true">⌕</span>
            <input id="search-input" type="search" placeholder="Tìm lệnh hoặc tổ hợp phím…" autocomplete="off" />
            <kbd>Ctrl F</kbd>
          </label>
          <label class="select-wrap control-rounded">
            <select id="group-select" aria-label="Lọc theo nhóm">
              <option>Tất cả nhóm</option>
            </select>
          </label>
          <label class="toggle-label">
            <input id="assigned-only" type="checkbox" />
            <span class="toggle" aria-hidden="true"></span>
            <span>Chỉ phím đã gán</span>
          </label>
        </div>

        <div class="table-surface surface">
          <div class="table-head hotkey-grid" aria-hidden="true">
            <span>NHÓM</span><span>LỆNH</span><span>HOTKEY</span><span>TRẠNG THÁI</span>
          </div>
          <div id="hotkey-list" class="hotkey-list" role="listbox" aria-label="Danh sách hotkey">
            <div class="loading-state"><span class="spinner"></span>Đang tải hotkey…</div>
          </div>
        </div>

        <section class="editor-card surface" aria-label="Chỉnh sửa hotkey">
          <div class="editor-heading">
            <div>
              <h2 id="selection-title">Chọn một lệnh để chỉnh sửa</h2>
              <p id="selection-meta">Bạn có thể tìm theo tên lệnh hoặc hotkey.</p>
            </div>
            <span id="dirty-pill" class="dirty-pill" hidden>ĐÃ SỬA</span>
          </div>
          <div class="editor-controls">
            <input id="hotkey-input" class="hotkey-input control-rounded" type="text" disabled aria-label="Hotkey hiện tại" />
            <button id="record-button" class="button button-primary" type="button" disabled>Ghi tổ hợp phím</button>
            <button id="clear-button" class="button button-secondary" type="button" disabled>Xóa gán</button>
            <button id="restore-button" class="button button-secondary" type="button" disabled>Khôi phục</button>
          </div>
          <div id="conflict-message" class="helper-text">Chưa có lệnh được chọn.</div>
        </section>
      </section>
    </section>

    <footer class="statusbar">
      <div class="status-message"><span id="status-dot" class="status-dot success"></span><span id="status-text">Sẵn sàng</span></div>
      <span id="count-text">0 lệnh</span>
    </footer>
  </main>

  <div id="dialog-backdrop" class="dialog-backdrop" hidden>
    <section class="dialog surface" role="dialog" aria-modal="true" aria-labelledby="dialog-title">
      <div id="dialog-icon" class="dialog-icon">S</div>
      <h2 id="dialog-title"></h2>
      <p id="dialog-message"></p>
      <input id="dialog-input" class="dialog-input control-rounded" type="text" hidden />
      <div class="dialog-actions">
        <button id="dialog-cancel" class="button button-secondary" type="button">Hủy</button>
        <button id="dialog-confirm" class="button button-primary" type="button">Xác nhận</button>
      </div>
    </section>
  </div>
  <div id="toast-region" class="toast-region" aria-live="polite"></div>
`;

const $ = <T extends HTMLElement>(selector: string): T => {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`Không tìm thấy phần tử ${selector}`);
  return element;
};

const targetPath = $("#target-path");
const reloadButton = $("#reload-button") as HTMLButtonElement;
const applyButton = $("#apply-button") as HTMLButtonElement;
const savePresetButton = $("#save-preset-button") as HTMLButtonElement;
const presetList = $("#preset-list");
const presetMeta = $("#preset-meta");
const searchInput = $("#search-input") as HTMLInputElement;
const groupSelect = $("#group-select") as HTMLSelectElement;
const assignedOnly = $("#assigned-only") as HTMLInputElement;
const hotkeyList = $("#hotkey-list");
const hotkeyInput = $("#hotkey-input") as HTMLInputElement;
const selectionTitle = $("#selection-title");
const selectionMeta = $("#selection-meta");
const dirtyPill = $("#dirty-pill");
const recordButton = $("#record-button") as HTMLButtonElement;
const clearButton = $("#clear-button") as HTMLButtonElement;
const restoreButton = $("#restore-button") as HTMLButtonElement;
const conflictMessage = $("#conflict-message");
const statusDot = $("#status-dot");
const statusText = $("#status-text");
const countText = $("#count-text");

let snapshot: HotkeySnapshot | null = null;
let selectedIndex: number | null = null;
let presets: PresetSummary[] = [];
let selectedPresetFile: string | null = null;
let activePresetFile: string | null = null;
let savedWorkingValues = new Map<string, string>();
let recording = false;

function hasUnappliedChanges(): boolean {
  return snapshot?.entries.some((entry) => entry.value !== entry.originalValue) ?? false;
}

function hasUnsavedPresetChanges(): boolean {
  return snapshot?.entries.some((entry) => savedWorkingValues.get(entry.entryId) !== entry.value) ?? false;
}

function hasUnsavedWork(): boolean {
  return hasUnappliedChanges() && (!activePresetFile || hasUnsavedPresetChanges());
}

function captureWorkingBaseline(): void {
  savedWorkingValues = new Map(snapshot?.entries.map((entry) => [entry.entryId, entry.value]) ?? []);
}

function selectedEntry(): HotkeyEntry | null {
  if (!snapshot || selectedIndex === null) return null;
  return snapshot.entries[selectedIndex] ?? null;
}

function setStatus(message: string, tone: "success" | "warning" | "error" = "success"): void {
  statusText.textContent = message;
  statusDot.className = `status-dot ${tone}`;
}

function toast(message: string, tone: "success" | "warning" | "error" = "success"): void {
  const region = $("#toast-region");
  const item = document.createElement("div");
  item.className = `toast ${tone}`;
  item.textContent = message;
  region.append(item);
  requestAnimationFrame(() => item.classList.add("visible"));
  window.setTimeout(() => {
    item.classList.remove("visible");
    window.setTimeout(() => item.remove(), 220);
  }, 3400);
}

function errorMessage(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error);
  return raw.replace(/^(SPINE_RUNNING|FILE_CHANGED|PRESET_EXISTS):/, "");
}

interface DialogOptions {
  title: string;
  message: string;
  confirmText?: string;
  inputValue?: string;
  danger?: boolean;
}

function openDialog(options: DialogOptions): Promise<boolean | string | null> {
  const backdrop = $("#dialog-backdrop");
  const title = $("#dialog-title");
  const message = $("#dialog-message");
  const icon = $("#dialog-icon");
  const input = $("#dialog-input") as HTMLInputElement;
  const cancel = $("#dialog-cancel") as HTMLButtonElement;
  const confirm = $("#dialog-confirm") as HTMLButtonElement;
  title.textContent = options.title;
  message.textContent = options.message;
  confirm.textContent = options.confirmText ?? "Xác nhận";
  confirm.className = `button ${options.danger ? "button-danger" : "button-primary"}`;
  icon.className = `dialog-icon ${options.danger ? "danger" : ""}`;
  const hasInput = options.inputValue !== undefined;
  input.hidden = !hasInput;
  input.value = options.inputValue ?? "";
  backdrop.hidden = false;

  return new Promise((resolve) => {
    const close = (value: boolean | string | null): void => {
      backdrop.hidden = true;
      cancel.removeEventListener("click", onCancel);
      confirm.removeEventListener("click", onConfirm);
      backdrop.removeEventListener("click", onBackdrop);
      document.removeEventListener("keydown", onKeydown);
      resolve(value);
    };
    const onCancel = (): void => close(null);
    const onConfirm = (): void => {
      if (hasInput && !input.value.trim()) {
        input.classList.add("invalid");
        input.focus();
        return;
      }
      close(hasInput ? input.value.trim() : true);
    };
    const onBackdrop = (event: Event): void => {
      if (event.target === backdrop) close(null);
    };
    const onKeydown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") close(null);
      if (event.key === "Enter") onConfirm();
    };
    cancel.addEventListener("click", onCancel);
    confirm.addEventListener("click", onConfirm);
    backdrop.addEventListener("click", onBackdrop);
    document.addEventListener("keydown", onKeydown);
    input.classList.remove("invalid");
    window.setTimeout(() => (hasInput ? input.select() : confirm.focus()), 20);
  });
}

function refreshGroups(): void {
  if (!snapshot) return;
  const current = groupSelect.value;
  const groups = [...new Set(snapshot.entries.map((entry) => entry.groupLabel))];
  groupSelect.replaceChildren();
  ["Tất cả nhóm", ...groups].forEach((group) => {
    const option = document.createElement("option");
    option.value = group;
    option.textContent = group;
    groupSelect.append(option);
  });
  groupSelect.value = groups.includes(current) ? current : "Tất cả nhóm";
}

function conflictIdsFor(entryId: string): string[] {
  if (!snapshot) return [];
  return [...findConflicts(snapshot.entries).values()].find((ids) => ids.includes(entryId)) ?? [];
}

function navigateToNextConflict(entryId: string): void {
  if (!snapshot) return;
  const related = conflictIdsFor(entryId);
  if (related.length < 2) return;
  const currentPosition = related.indexOf(entryId);
  const targetId = related[(currentPosition + 1) % related.length];
  const targetIndex = snapshot.entries.findIndex((entry) => entry.entryId === targetId);
  if (targetIndex < 0) return;

  const target = snapshot.entries[targetIndex];
  const query = searchInput.value.trim().toLocaleLowerCase();
  const haystack = `${target.groupLabel} ${target.action} ${target.value}`.toLocaleLowerCase();
  if (query && !haystack.includes(query)) searchInput.value = "";
  if (groupSelect.value !== "Tất cả nhóm" && groupSelect.value !== target.groupLabel) {
    groupSelect.value = "Tất cả nhóm";
  }

  selectedIndex = targetIndex;
  stopRecording();
  refreshEditor();
  refreshTable();
  window.requestAnimationFrame(() => {
    hotkeyList.querySelector<HTMLElement>(`[data-index="${targetIndex}"]`)?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
  });
}

function refreshTable(): void {
  if (!snapshot) return;
  const query = searchInput.value.trim().toLocaleLowerCase();
  const group = groupSelect.value;
  const conflicts = findConflicts(snapshot.entries);
  const conflictIds = new Set([...conflicts.values()].flat());
  const fragment = document.createDocumentFragment();
  let shown = 0;
  let assigned = 0;

  snapshot.entries.forEach((entry, index) => {
    if (entry.value) assigned += 1;
    if (group !== "Tất cả nhóm" && entry.groupLabel !== group) return;
    if (assignedOnly.checked && !entry.value) return;
    const haystack = `${entry.groupLabel} ${entry.action} ${entry.value}`.toLocaleLowerCase();
    if (query && !haystack.includes(query)) return;

    const row = document.createElement("div");
    row.className = "hotkey-row hotkey-grid";
    row.dataset.index = String(index);
    row.setAttribute("role", "option");
    row.tabIndex = 0;
    row.setAttribute("aria-selected", String(index === selectedIndex));
    if (index === selectedIndex) row.classList.add("selected");
    if (conflictIds.has(entry.entryId)) row.classList.add("conflict");
    if (entry.value !== entry.originalValue) row.classList.add("changed");

    const groupCell = document.createElement("span");
    groupCell.className = "group-cell";
    groupCell.textContent = entry.groupLabel;
    const actionCell = document.createElement("span");
    actionCell.className = "action-cell";
    actionCell.textContent = entry.action;
    const keyCell = document.createElement("span");
    keyCell.className = "key-cell";
    const keycap = document.createElement("kbd");
    keycap.textContent = entry.value || "Chưa gán";
    if (!entry.value) keycap.classList.add("empty");
    keyCell.append(keycap);
    const stateCell = document.createElement("span");
    stateCell.className = "state-cell";
    const stateText = conflictIds.has(entry.entryId)
      ? "Trùng phím"
      : entry.value !== entry.originalValue
        ? "Đã sửa"
        : "";
    if (stateText) {
      if (conflictIds.has(entry.entryId)) {
        const stateChip = document.createElement("button");
        stateChip.type = "button";
        stateChip.className = "state-chip conflict";
        stateChip.textContent = "Trùng phím →";
        stateChip.title = "Đi tới lệnh tiếp theo dùng cùng tổ hợp phím";
        stateChip.addEventListener("click", (event) => {
          event.stopPropagation();
          navigateToNextConflict(entry.entryId);
        });
        stateChip.addEventListener("dblclick", (event) => event.stopPropagation());
        stateCell.append(stateChip);
      } else {
        const stateChip = document.createElement("span");
        stateChip.className = "state-chip changed";
        stateChip.textContent = stateText;
        stateCell.append(stateChip);
      }
    }
    row.append(groupCell, actionCell, keyCell, stateCell);
    row.addEventListener("click", () => selectEntry(index));
    row.addEventListener("dblclick", () => startRecording());
    row.addEventListener("keydown", (event) => {
      if (event.target !== row || !["Enter", " "].includes(event.key)) return;
      event.preventDefault();
      selectEntry(index);
    });
    fragment.append(row);
    shown += 1;
  });

  hotkeyList.replaceChildren(fragment);
  if (!shown) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Không tìm thấy lệnh phù hợp.";
    hotkeyList.append(empty);
  }
  countText.textContent = `Hiển thị ${shown}/${snapshot.entries.length} · Đã gán ${assigned}`;
  updateDirtyState();
}

function selectEntry(index: number): void {
  selectedIndex = index;
  stopRecording();
  refreshEditor();
  refreshTable();
}

function refreshEditor(): void {
  const entry = selectedEntry();
  const disabled = !entry;
  hotkeyInput.disabled = disabled;
  recordButton.disabled = disabled;
  clearButton.disabled = disabled;
  restoreButton.disabled = disabled;
  if (!entry) {
    selectionTitle.textContent = "Chọn một lệnh để chỉnh sửa";
    selectionMeta.textContent = "Bạn có thể tìm theo tên lệnh hoặc hotkey.";
    hotkeyInput.value = "";
    conflictMessage.textContent = "Chưa có lệnh được chọn.";
    dirtyPill.hidden = true;
    return;
  }
  selectionTitle.textContent = entry.action;
  selectionMeta.textContent = `${entry.groupLabel}${entry.actionOccurrence > 1 ? ` · lựa chọn ${entry.actionOccurrence}` : ""}`;
  hotkeyInput.value = entry.value;
  dirtyPill.hidden = entry.value === entry.originalValue;
  updateConflictMessage(entry);
}

function updateConflictMessage(entry: HotkeyEntry): void {
  if (!snapshot) return;
  if (!entry.value) {
    conflictMessage.className = "helper-text";
    conflictMessage.textContent = "Chưa gán phím. Nhấn “Ghi tổ hợp phím” để nhập nhanh.";
    return;
  }
  const conflicts = findConflicts(snapshot.entries);
  const related = [...conflicts.values()].find((ids) => ids.includes(entry.entryId));
  if (related) {
    const names = related
      .filter((id) => id !== entry.entryId)
      .map((id) => snapshot?.entries.find((candidate) => candidate.entryId === id)?.action)
      .filter(Boolean)
      .slice(0, 3);
    conflictMessage.className = "helper-text warning";
    const copy = document.createElement("span");
    copy.textContent = `Cảnh báo: trùng với ${names.join(", ")}`;
    const actions = document.createElement("span");
    actions.className = "helper-actions";
    const navigateButton = document.createElement("button");
    navigateButton.type = "button";
    navigateButton.className = "helper-action";
    navigateButton.textContent = "Đi tới";
    navigateButton.addEventListener("click", () => navigateToNextConflict(entry.entryId));
    const overrideButton = document.createElement("button");
    overrideButton.type = "button";
    overrideButton.className = "helper-action danger";
    overrideButton.textContent = "Ghi đè";
    overrideButton.addEventListener("click", () => void overrideSelectedConflict());
    actions.append(navigateButton, overrideButton);
    conflictMessage.replaceChildren(copy, actions);
  } else {
    conflictMessage.className = "helper-text success";
    conflictMessage.textContent = "Không phát hiện xung đột phím.";
  }
}

async function overrideSelectedConflict(): Promise<void> {
  if (!snapshot) return;
  commitManualValue();
  const entry = selectedEntry();
  if (!entry?.value) return;
  const otherIds = conflictIdsFor(entry.entryId).filter((id) => id !== entry.entryId);
  if (!otherIds.length) return;
  const affected = otherIds
    .map((id) => snapshot?.entries.find((candidate) => candidate.entryId === id)?.action)
    .filter((name): name is string => Boolean(name));
  const confirmed = await openDialog({
    title: "Ghi đè tổ hợp phím?",
    message: `Giữ “${entry.value}” cho “${entry.action}” và xóa khỏi ${affected.length} lệnh: ${affected.join(", ")}.`,
    confirmText: "Ghi đè",
    danger: true,
  });
  if (!confirmed) return;
  overrideConflict(snapshot.entries, entry.entryId);
  refreshEditor();
  refreshTable();
  setStatus(`Đã ưu tiên “${entry.action}”; ${affected.length} lệnh trùng đã được xóa phím`, "warning");
  toast(`Đã xóa tổ hợp khỏi ${affected.length} lệnh bị trùng`);
}

function updateDirtyState(): void {
  if (!snapshot) return;
  const changed = snapshot.entries.filter((entry) => entry.value !== entry.originalValue).length;
  const unsavedPreset = activePresetFile ? hasUnsavedPresetChanges() : changed > 0;
  applyButton.classList.toggle("has-changes", changed > 0);
  savePresetButton.classList.toggle("has-changes", unsavedPreset);
  if (changed > 0) {
    setStatus(`${changed} thay đổi chưa áp dụng${unsavedPreset ? " · preset chưa lưu" : ""}`, "warning");
  } else if (unsavedPreset) {
    setStatus("Preset có thay đổi chưa lưu", "warning");
  }
}

function commitManualValue(): void {
  const entry = selectedEntry();
  if (!entry) return;
  entry.value = cleanHotkey(hotkeyInput.value);
  hotkeyInput.value = entry.value;
  refreshEditor();
  refreshTable();
}

function startRecording(): void {
  if (!selectedEntry()) return;
  recording = true;
  recordButton.textContent = "Đang nghe phím…";
  recordButton.classList.add("recording");
  conflictMessage.className = "helper-text recording";
  conflictMessage.textContent = "Nhấn tổ hợp mong muốn. Ctrl, Shift và Alt đều được hỗ trợ.";
  hotkeyInput.focus();
}

function stopRecording(): void {
  recording = false;
  recordButton.textContent = "Ghi tổ hợp phím";
  recordButton.classList.remove("recording");
}

async function loadDocument(force = false): Promise<void> {
  if (!force && hasUnsavedWork()) {
    const confirmed = await openDialog({
      title: "Tải lại hotkeys.txt?",
      message: "Các thay đổi chưa lưu vào preset hoặc Spine sẽ bị bỏ.",
      confirmText: "Tải lại",
    });
    if (!confirmed) return;
  }
  reloadButton.disabled = true;
  setStatus("Đang đọc hotkeys.txt…");
  try {
    snapshot = await invoke<HotkeySnapshot>("load_hotkeys");
    selectedIndex = null;
    activePresetFile = null;
    targetPath.textContent = snapshot.path;
    searchInput.value = "";
    groupSelect.value = "Tất cả nhóm";
    refreshGroups();
    captureWorkingBaseline();
    renderPresets();
    refreshTable();
    refreshEditor();
    setStatus(`Đã đọc ${snapshot.entries.length} lệnh`);
  } catch (error) {
    const message = errorMessage(error);
    setStatus(message, "error");
    await openDialog({ title: "Không thể mở hotkeys.txt", message, confirmText: "Đóng" });
  } finally {
    reloadButton.disabled = false;
  }
}

async function applyChanges(): Promise<void> {
  if (!snapshot) return;
  commitManualValue();
  if (!hasUnappliedChanges()) {
    toast("Không có thay đổi để áp dụng", "warning");
    return;
  }
  const conflictCount = findConflicts(snapshot.entries).size;
  if (conflictCount) {
    const confirmed = await openDialog({
      title: "Có hotkey bị trùng",
      message: `Đang có ${conflictCount} tổ hợp phím bị trùng. Bạn vẫn muốn áp dụng?`,
      confirmText: "Vẫn áp dụng",
    });
    if (!confirmed) return;
  }
  applyButton.disabled = true;
  setStatus("Đang tạo backup và áp dụng…");
  try {
    const result = await invoke<SaveHotkeysResult>("save_hotkeys", {
      request: {
        sourceToken: snapshot.sourceToken,
        bindings: bindingRecord(snapshot.entries),
      },
    });
    snapshot.sourceToken = result.sourceToken;
    snapshot.entries.forEach((entry) => (entry.originalValue = entry.value));
    refreshTable();
    refreshEditor();
    setStatus(`Đã áp dụng ${result.updatedCount} thay đổi`);
    toast("Đã cập nhật hotkeys.txt và tạo backup");
  } catch (error) {
    const raw = String(error);
    const message = errorMessage(error);
    setStatus(message, "error");
    await openDialog({
      title: raw.startsWith("SPINE_RUNNING:") ? "Hãy đóng Spine" : "Chưa thể áp dụng",
      message,
      confirmText: "Đã hiểu",
    });
    if (raw.startsWith("FILE_CHANGED:")) await loadDocument(true);
  } finally {
    applyButton.disabled = false;
  }
}

function renderPresets(): void {
  presetList.replaceChildren();
  if (!presets.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state compact";
    empty.textContent = "Chưa có preset";
    presetList.append(empty);
    presetMeta.textContent = "Chỉnh hotkey rồi lưu bộ đầu tiên.";
    selectedPresetFile = null;
    activePresetFile = null;
    return;
  }
  presets.forEach((preset) => {
    const item = document.createElement("div");
    item.className = "preset-item";
    item.setAttribute("role", "listitem");
    if (preset.fileName === selectedPresetFile) item.classList.add("selected");
    if (preset.fileName === activePresetFile) item.classList.add("active");
    const loadButton = document.createElement("button");
    loadButton.type = "button";
    loadButton.className = "preset-load";
    loadButton.setAttribute("aria-label", `Nạp preset ${preset.name}`);
    const mark = document.createElement("span");
    mark.className = "preset-mark";
    mark.textContent = preset.name.slice(0, 1).toLocaleUpperCase();
    const copy = document.createElement("span");
    const name = document.createElement("strong");
    name.textContent = preset.name;
    const count = document.createElement("small");
    count.textContent = `${preset.bindingCount} lệnh${preset.fileName === activePresetFile ? " · Đang dùng" : ""}`;
    copy.append(name, count);
    loadButton.append(mark, copy);
    loadButton.addEventListener("click", () => void loadPreset(preset.fileName));
    const renameButton = document.createElement("button");
    renameButton.type = "button";
    renameButton.className = "preset-item-action preset-rename";
    renameButton.title = `Đổi tên preset ${preset.name}`;
    renameButton.setAttribute("aria-label", `Đổi tên preset ${preset.name}`);
    renameButton.innerHTML = `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 20h4l10.6-10.6a1.4 1.4 0 0 0 0-2L16.6 5.4a1.4 1.4 0 0 0-2 0L4 16v4Zm9.5-12.5 3 3" />
      </svg>
    `;
    renameButton.addEventListener("click", () => void renamePreset(preset));
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "preset-item-action preset-delete";
    deleteButton.title = `Xóa preset ${preset.name}`;
    deleteButton.setAttribute("aria-label", `Xóa preset ${preset.name}`);
    deleteButton.innerHTML = `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 7h16M9 7V4h6v3m-9 0 1 13h10l1-13M10 11v5m4-5v5" />
      </svg>
    `;
    deleteButton.addEventListener("click", () => void deletePreset(preset));
    item.append(loadButton, renameButton, deleteButton);
    presetList.append(item);
  });
  const selected = presets.find((preset) => preset.fileName === selectedPresetFile);
  if (selected) {
    const date = new Date(selected.createdAt);
    presetMeta.textContent = `${selected.bindingCount} lệnh · ${date.toLocaleString("vi-VN")}`;
  } else {
    presetMeta.textContent = "Chọn một preset để nạp.";
  }
}

async function refreshPresets(preferred?: string): Promise<void> {
  try {
    presets = await invoke<PresetSummary[]>("list_presets");
    if (preferred && presets.some((preset) => preset.fileName === preferred)) selectedPresetFile = preferred;
    else if (selectedPresetFile && !presets.some((preset) => preset.fileName === selectedPresetFile)) selectedPresetFile = null;
    if (activePresetFile && !presets.some((preset) => preset.fileName === activePresetFile)) activePresetFile = null;
    renderPresets();
  } catch (error) {
    toast(errorMessage(error), "error");
  }
}

function currentPreset(): PresetSummary | null {
  return presets.find((preset) => preset.fileName === selectedPresetFile) ?? null;
}

function activePreset(): PresetSummary | null {
  return presets.find((preset) => preset.fileName === activePresetFile) ?? null;
}

function presetRequest(name: string, overwrite: boolean): {
  name: string;
  sourceFile: string;
  structureFingerprint: string;
  bindings: Record<string, string>;
  overwrite: boolean;
} | null {
  if (!snapshot) return null;
  return {
    name,
    sourceFile: snapshot.path.split(/[\\/]/).pop() ?? "hotkeys.txt",
    structureFingerprint: snapshot.structureFingerprint,
    bindings: bindingRecord(snapshot.entries),
    overwrite,
  };
}

async function saveActivePreset(): Promise<void> {
  if (!snapshot) return;
  commitManualValue();
  const preset = activePreset();
  if (!preset) {
    await createPreset();
    return;
  }
  const request = presetRequest(preset.name, true);
  if (!request) return;
  savePresetButton.disabled = true;
  try {
    const summary = await invoke<PresetSummary>("save_preset", { request });
    activePresetFile = summary.fileName;
    captureWorkingBaseline();
    await refreshPresets(selectedPresetFile ?? summary.fileName);
    updateDirtyState();
    setStatus(`Đã lưu preset “${summary.name}”${hasUnappliedChanges() ? " · chưa áp dụng vào Spine" : ""}`);
    toast(`Đã cập nhật preset “${summary.name}”`);
  } catch (error) {
    toast(errorMessage(error), "error");
  } finally {
    savePresetButton.disabled = false;
  }
}

async function createPreset(): Promise<void> {
  if (!snapshot) return;
  commitManualValue();
  const name = await openDialog({
    title: "Lưu preset mới",
    message: "Đặt tên dễ nhớ cho bộ hotkey hiện tại.",
    confirmText: "Lưu preset",
    inputValue: "Preset mới",
  });
  if (typeof name !== "string") return;
  const request = presetRequest(name, false);
  if (!request) return;
  try {
    const summary = await invoke<PresetSummary>("save_preset", { request });
    activePresetFile = summary.fileName;
    captureWorkingBaseline();
    await refreshPresets(summary.fileName);
    updateDirtyState();
    toast(`Đã lưu preset “${summary.name}”`);
  } catch (error) {
    if (String(error).startsWith("PRESET_EXISTS:")) {
      const overwrite = await openDialog({
        title: "Preset đã tồn tại",
        message: `Bạn có muốn ghi đè preset “${name}”?`,
        confirmText: "Ghi đè",
      });
      if (overwrite) {
        request.overwrite = true;
        const summary = await invoke<PresetSummary>("save_preset", { request });
        activePresetFile = summary.fileName;
        captureWorkingBaseline();
        await refreshPresets(summary.fileName);
        updateDirtyState();
        toast(`Đã cập nhật preset “${summary.name}”`);
      }
    } else toast(errorMessage(error), "error");
  }
}

async function loadPreset(fileName: string): Promise<void> {
  if (!snapshot) return;
  const preset = presets.find((candidate) => candidate.fileName === fileName);
  if (!preset) return;
  if (fileName === activePresetFile) {
    selectedPresetFile = fileName;
    renderPresets();
    return;
  }
  if (hasUnsavedWork()) {
    const confirmed = await openDialog({
      title: "Chuyển sang preset khác?",
      message: "Các thay đổi chưa lưu vào preset hoặc Spine sẽ bị bỏ.",
      confirmText: "Chuyển preset",
    });
    if (!confirmed) return;
  }
  try {
    const payload = await invoke<PresetPayload>("load_preset", { fileName });
    if (payload.structureFingerprint !== snapshot.structureFingerprint) {
      const confirmed = await openDialog({
        title: "Preset khác phiên bản",
        message: "Tool chỉ nạp những lệnh còn khớp với file hiện tại. Tiếp tục?",
        confirmText: "Nạp phần khớp",
      });
      if (!confirmed) return;
    }
    let matched = 0;
    snapshot.entries.forEach((entry) => {
      if (Object.hasOwn(payload.bindings, entry.entryId)) {
        entry.value = cleanHotkey(payload.bindings[entry.entryId]);
        matched += 1;
      }
    });
    selectedPresetFile = fileName;
    activePresetFile = fileName;
    captureWorkingBaseline();
    renderPresets();
    refreshTable();
    refreshEditor();
    setStatus(`Đã nạp ${matched} lệnh từ preset`, "warning");
    toast(`Đã nạp preset “${payload.name}”`);
  } catch (error) {
    toast(errorMessage(error), "error");
  }
}

async function renamePreset(preset: PresetSummary): Promise<void> {
  const newName = await openDialog({
    title: "Đổi tên preset",
    message: "Nhập tên mới cho bộ hotkey.",
    confirmText: "Đổi tên",
    inputValue: preset.name,
  });
  if (typeof newName !== "string" || newName === preset.name) return;
  try {
    const wasActive = activePresetFile === preset.fileName;
    const summary = await invoke<PresetSummary>("rename_preset", {
      request: { fileName: preset.fileName, newName },
    });
    if (wasActive) activePresetFile = summary.fileName;
    await refreshPresets(wasActive ? summary.fileName : (activePresetFile ?? undefined));
    toast(`Đã đổi tên thành “${summary.name}”`);
  } catch (error) {
    toast(errorMessage(error), "error");
  }
}

async function duplicatePreset(): Promise<void> {
  const preset = currentPreset();
  if (!preset) return toast("Hãy chọn một preset", "warning");
  const newName = await openDialog({
    title: "Sao chép preset",
    message: "Đặt tên cho bản sao.",
    confirmText: "Tạo bản sao",
    inputValue: `${preset.name} - Copy`,
  });
  if (typeof newName !== "string") return;
  try {
    const summary = await invoke<PresetSummary>("duplicate_preset", {
      request: { fileName: preset.fileName, newName },
    });
    await refreshPresets(activePresetFile ?? undefined);
    toast(`Đã tạo “${summary.name}”`);
  } catch (error) {
    toast(errorMessage(error), "error");
  }
}

async function deletePreset(preset: PresetSummary): Promise<void> {
  const confirmed = await openDialog({
    title: "Xóa preset?",
    message: `Preset “${preset.name}” sẽ bị xóa. hotkeys.txt không bị ảnh hưởng.`,
    confirmText: "Xóa preset",
    danger: true,
  });
  if (!confirmed) return;
  try {
    await invoke("delete_preset", { fileName: preset.fileName });
    if (activePresetFile === preset.fileName) activePresetFile = null;
    if (selectedPresetFile === preset.fileName) selectedPresetFile = null;
    await refreshPresets(activePresetFile ?? selectedPresetFile ?? undefined);
    toast(`Đã xóa preset “${preset.name}”`);
  } catch (error) {
    toast(errorMessage(error), "error");
  }
}

searchInput.addEventListener("input", refreshTable);
groupSelect.addEventListener("change", refreshTable);
assignedOnly.addEventListener("change", refreshTable);
reloadButton.addEventListener("click", () => void loadDocument());
applyButton.addEventListener("click", () => void applyChanges());
hotkeyInput.addEventListener("change", commitManualValue);
hotkeyInput.addEventListener("keydown", (event) => {
  if (!recording && event.key === "Enter") commitManualValue();
});
recordButton.addEventListener("click", () => (recording ? stopRecording() : startRecording()));
clearButton.addEventListener("click", () => {
  const entry = selectedEntry();
  if (!entry) return;
  entry.value = "";
  refreshEditor();
  refreshTable();
});
restoreButton.addEventListener("click", () => {
  const entry = selectedEntry();
  if (!entry) return;
  entry.value = entry.originalValue;
  refreshEditor();
  refreshTable();
});
savePresetButton.addEventListener("click", () => void saveActivePreset());
$("#save-as-preset-button").addEventListener("click", () => void createPreset());
$("#duplicate-preset-button").addEventListener("click", () => void duplicatePreset());

document.addEventListener(
  "keydown",
  (event) => {
    if (!recording) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const hotkey = eventToSpineHotkey(event);
    if (hotkey === null) return;
    if (!hotkey) {
      toast(`Phím ${event.code} chưa được hỗ trợ; bạn có thể nhập tay`, "warning");
      return;
    }
    const entry = selectedEntry();
    if (!entry) return;
    entry.value = hotkey;
    stopRecording();
    refreshEditor();
    refreshTable();
    setStatus(`Đã ghi tổ hợp ${hotkey}`, "warning");
  },
  true,
);

document.addEventListener("keydown", (event) => {
  if (event.ctrlKey && event.key.toLocaleLowerCase() === "s" && !recording) {
    event.preventDefault();
    void saveActivePreset();
    return;
  }
  if (event.ctrlKey && event.key.toLocaleLowerCase() === "f" && !recording) {
    event.preventDefault();
    searchInput.focus();
    searchInput.select();
  }
});

window.addEventListener("beforeunload", (event) => {
  if (hasUnsavedWork()) event.preventDefault();
});

void Promise.all([loadDocument(true), refreshPresets()]);
