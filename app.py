from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from hotkey_core import (
    HotkeyDocument,
    apply_preset,
    find_conflicts,
    load_preset,
    safe_preset_filename,
    save_preset,
)


APP_DIR = Path(__file__).resolve().parent
DEFAULT_HOTKEY_FILE = APP_DIR.parent / "hotkeys.txt"
PRESET_DIR = APP_DIR / "presets"
BACKUP_DIR = APP_DIR / "backups"

BG = "#0B0F17"
PANEL = "#111827"
PANEL_2 = "#151E2E"
INPUT = "#0E1624"
BORDER = "#263247"
TEXT = "#E6EDF7"
MUTED = "#8C9AAF"
ACCENT = "#7C5CFC"
ACCENT_HOVER = "#8E73FF"
GREEN = "#31C48D"
RED = "#F97066"
AMBER = "#F6C453"
ROW_ALT = "#121B2A"


def _rounded_points(x1: float, y1: float, x2: float, y2: float, radius: float) -> list[float]:
    radius = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]


class RoundedPanel(tk.Canvas):
    def __init__(
        self,
        parent,
        *,
        outer_bg: str,
        fill: str,
        radius: int = 16,
        inset: int = 8,
        border: str = BORDER,
        width: int = 1,
        height: int = 1,
    ) -> None:
        super().__init__(
            parent,
            bg=outer_bg,
            highlightthickness=0,
            borderwidth=0,
            width=width,
            height=height,
        )
        self.fill = fill
        self.radius = radius
        self.inset = inset
        self.border = border
        self.content = tk.Frame(self, bg=fill, borderwidth=0, highlightthickness=0)
        self._window = self.create_window(inset, inset, window=self.content, anchor="nw")
        self.bind("<Configure>", self._redraw)

    def _redraw(self, event=None) -> None:
        width = max(2, event.width if event else self.winfo_width())
        height = max(2, event.height if event else self.winfo_height())
        self.delete("rounded-bg")
        self.create_polygon(
            _rounded_points(1, 1, width - 1, height - 1, self.radius),
            smooth=True,
            splinesteps=24,
            fill=self.border,
            outline="",
            tags="rounded-bg",
        )
        self.create_polygon(
            _rounded_points(2, 2, width - 2, height - 2, max(0, self.radius - 1)),
            smooth=True,
            splinesteps=24,
            fill=self.fill,
            outline="",
            tags="rounded-bg",
        )
        self.tag_lower("rounded-bg")
        available_width = max(1, width - self.inset * 2)
        available_height = max(1, height - self.inset * 2)
        self.coords(self._window, self.inset, self.inset)
        self.itemconfigure(self._window, width=available_width, height=available_height)


class RoundedButton(tk.Canvas):
    def __init__(
        self,
        parent,
        text: str,
        command,
        *,
        width: int,
        height: int = 38,
        radius: int = 11,
        outer_bg: str,
        fill: str = PANEL_2,
        hover: str = "#202B3E",
        foreground: str = TEXT,
        border: str | None = BORDER,
        font=("Segoe UI Semibold", 9),
    ) -> None:
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=outer_bg,
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
        )
        self.button_text = text
        self.command = command
        self.radius = radius
        self.fill = fill
        self.hover = hover
        self.foreground = foreground
        self.border = border
        self.font_spec = font
        self.enabled = True
        self.bind("<Configure>", lambda _event: self._draw(self.fill))
        self.bind("<Enter>", lambda _event: self._draw(self.hover) if self.enabled else None)
        self.bind("<Leave>", lambda _event: self._draw(self.fill) if self.enabled else None)
        self.bind("<Button-1>", self._on_click)
        self._draw(self.fill)

    def _draw(self, color: str) -> None:
        width = max(2, self.winfo_width())
        height = max(2, self.winfo_height())
        self.delete("all")
        if self.border:
            self.create_polygon(
                _rounded_points(0, 0, width, height, self.radius),
                smooth=True,
                splinesteps=24,
                fill=self.border,
                outline="",
            )
            inset = 1
        else:
            inset = 0
        self.create_polygon(
            _rounded_points(inset, inset, width - inset, height - inset, max(0, self.radius - inset)),
            smooth=True,
            splinesteps=24,
            fill=color if self.enabled else BORDER,
            outline="",
        )
        self.create_text(
            width / 2,
            height / 2,
            text=self.button_text,
            fill=self.foreground if self.enabled else MUTED,
            font=self.font_spec,
        )

    def _on_click(self, _event=None) -> None:
        if self.enabled and self.command:
            self.command()

    def configure(self, cnf=None, **kwargs):
        if cnf:
            kwargs.update(cnf)
        if "text" in kwargs:
            self.button_text = kwargs.pop("text")
        if "state" in kwargs:
            self.enabled = kwargs.pop("state") != "disabled"
        if kwargs:
            super().configure(**kwargs)
        self._draw(self.fill)

    config = configure


class HotkeyStudio:
    def __init__(self, root: tk.Tk, hotkey_path: Path) -> None:
        self.root = root
        self.hotkey_path = hotkey_path.resolve()
        self.document: HotkeyDocument | None = None
        self.selected_entry_id: str | None = None
        self.iid_to_entry_id: dict[str, str] = {}
        self.preset_paths: list[Path] = []
        self.recording = False
        self._setting_editor = False

        self.search_var = tk.StringVar()
        self.group_var = tk.StringVar(value="Tất cả nhóm")
        self.assigned_only_var = tk.BooleanVar(value=False)
        self.hotkey_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Sẵn sàng")
        self.count_var = tk.StringVar()
        self.selection_title_var = tk.StringVar(value="Chọn một lệnh để chỉnh sửa")
        self.selection_meta_var = tk.StringVar(value="Bạn có thể tìm theo tên lệnh hoặc hotkey.")
        self.conflict_var = tk.StringVar(value="")
        self.preset_meta_var = tk.StringVar(value="Chưa chọn preset")

        self._configure_root()
        self._configure_styles()
        self._build_ui()
        self._bind_events()
        self.reload_document(force=True)
        self.refresh_presets()

    def _configure_root(self) -> None:
        self.root.title("Spine Hotkey Studio")
        self.root.geometry("1280x820")
        self.root.minsize(1040, 680)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("App.TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("Panel2.TFrame", background=PANEL_2)
        style.configure("TSeparator", background=BORDER)
        style.configure(
            "Primary.TButton",
            background=ACCENT,
            foreground="#FFFFFF",
            borderwidth=0,
            focusthickness=0,
            padding=(16, 10),
            font=("Segoe UI Semibold", 10),
        )
        style.map("Primary.TButton", background=[("active", ACCENT_HOVER), ("disabled", BORDER)])
        style.configure(
            "Secondary.TButton",
            background=PANEL_2,
            foreground=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            borderwidth=1,
            focusthickness=0,
            padding=(12, 9),
            font=("Segoe UI", 9),
        )
        style.map("Secondary.TButton", background=[("active", "#202B3E")])
        style.configure(
            "Danger.TButton",
            background="#3A1D24",
            foreground="#FFB4AE",
            borderwidth=0,
            padding=(10, 8),
            font=("Segoe UI", 9),
        )
        style.map("Danger.TButton", background=[("active", "#52242C")])
        style.configure(
            "TEntry",
            fieldbackground=INPUT,
            foreground=TEXT,
            insertcolor=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=(10, 8),
        )
        style.map("TEntry", bordercolor=[("focus", ACCENT)])
        style.configure(
            "TCombobox",
            fieldbackground=INPUT,
            background=INPUT,
            foreground=TEXT,
            arrowcolor=MUTED,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=(8, 7),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", INPUT)],
            selectbackground=[("readonly", INPUT)],
            selectforeground=[("readonly", TEXT)],
        )
        style.configure(
            "Treeview",
            background=PANEL,
            fieldbackground=PANEL,
            foreground=TEXT,
            borderwidth=0,
            rowheight=37,
            font=("Segoe UI", 9),
        )
        style.map("Treeview", background=[("selected", "#312A5E")], foreground=[("selected", "#FFFFFF")])
        style.configure(
            "Treeview.Heading",
            background=PANEL_2,
            foreground=MUTED,
            borderwidth=0,
            relief="flat",
            padding=(10, 10),
            font=("Segoe UI Semibold", 9),
        )
        style.map("Treeview.Heading", background=[("active", PANEL_2)])
        style.configure("Vertical.TScrollbar", background=PANEL_2, troughcolor=PANEL, borderwidth=0, arrowcolor=MUTED)
        style.configure("Dark.TCheckbutton", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.map("Dark.TCheckbutton", background=[("active", BG)], foreground=[("active", TEXT)])

        self.root.option_add("*TCombobox*Listbox.background", INPUT)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=(22, 18, 22, 16))
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer, style="App.TFrame")
        header.pack(fill="x", pady=(0, 16))
        brand = ttk.Frame(header, style="App.TFrame")
        brand.pack(side="left")
        tk.Label(
            brand,
            text="S",
            width=3,
            height=1,
            bg=ACCENT,
            fg="#FFFFFF",
            font=("Segoe UI Black", 17),
            padx=3,
            pady=4,
        ).pack(side="left", padx=(0, 12))
        title_box = ttk.Frame(brand, style="App.TFrame")
        title_box.pack(side="left")
        tk.Label(title_box, text="Spine Hotkey Studio", bg=BG, fg=TEXT, font=("Segoe UI Semibold", 17)).pack(anchor="w")
        tk.Label(
            title_box,
            text=str(self.hotkey_path),
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(2, 0))

        RoundedButton(
            header,
            "Áp dụng vào Spine",
            self.apply_to_spine,
            width=164,
            height=42,
            radius=13,
            outer_bg=BG,
            fill=ACCENT,
            hover=ACCENT_HOVER,
            border=None,
            foreground="#FFFFFF",
            font=("Segoe UI Semibold", 10),
        ).pack(side="right")
        RoundedButton(
            header,
            "Tải lại",
            self.reload_document,
            width=88,
            height=42,
            radius=13,
            outer_bg=BG,
        ).pack(side="right", padx=(0, 9))

        body = ttk.Frame(outer, style="App.TFrame")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self._build_sidebar(body)
        self._build_workspace(body)

        footer = ttk.Frame(outer, style="App.TFrame")
        footer.pack(fill="x", pady=(12, 0))
        self.status_dot = tk.Label(footer, text="●", bg=BG, fg=GREEN, font=("Segoe UI", 9))
        self.status_dot.pack(side="left")
        tk.Label(footer, textvariable=self.status_var, bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(6, 0))
        tk.Label(footer, textvariable=self.count_var, bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="right")

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        sidebar_panel = RoundedPanel(parent, outer_bg=BG, fill=PANEL, radius=20, inset=16, width=244)
        sidebar_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        sidebar_panel.grid_propagate(False)
        sidebar = sidebar_panel.content
        sidebar.grid_rowconfigure(2, weight=1)
        sidebar.grid_columnconfigure(0, weight=1)

        tk.Label(sidebar, text="PRESET", bg=PANEL, fg=MUTED, font=("Segoe UI Semibold", 9)).grid(row=0, column=0, sticky="w")
        tk.Label(
            sidebar,
            text="Các bộ phím của bạn",
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI Semibold", 12),
        ).grid(row=1, column=0, sticky="w", pady=(4, 13))

        list_panel = RoundedPanel(sidebar, outer_bg=PANEL, fill=INPUT, radius=13, inset=6, border=BORDER)
        list_panel.grid(row=2, column=0, sticky="nsew")
        list_frame = list_panel.content
        self.preset_list = tk.Listbox(
            list_frame,
            bg=INPUT,
            fg=TEXT,
            selectbackground="#312A5E",
            selectforeground="#FFFFFF",
            highlightthickness=0,
            borderwidth=0,
            activestyle="none",
            font=("Segoe UI", 10),
            exportselection=False,
        )
        self.preset_list.pack(fill="both", expand=True, padx=5, pady=5)

        tk.Label(
            sidebar,
            textvariable=self.preset_meta_var,
            bg=PANEL,
            fg=MUTED,
            justify="left",
            wraplength=208,
            font=("Segoe UI", 8),
        ).grid(row=3, column=0, sticky="ew", pady=(10, 8))

        RoundedButton(
            sidebar,
            "Nạp preset đã chọn",
            self.load_selected_preset,
            width=210,
            outer_bg=PANEL,
            fill=ACCENT,
            hover=ACCENT_HOVER,
            border=None,
            foreground="#FFFFFF",
        ).grid(row=4, column=0, sticky="ew", pady=(0, 8))
        RoundedButton(
            sidebar,
            "Lưu thành preset mới",
            self.create_preset,
            width=210,
            outer_bg=PANEL,
        ).grid(row=5, column=0, sticky="ew", pady=(0, 8))

        preset_actions = ttk.Frame(sidebar, style="Panel.TFrame")
        preset_actions.grid(row=6, column=0, sticky="ew")
        for column in range(2):
            preset_actions.grid_columnconfigure(column, weight=1)
        RoundedButton(
            preset_actions,
            "Đổi tên",
            self.rename_preset,
            width=101,
            height=35,
            radius=10,
            outer_bg=PANEL,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 6))
        RoundedButton(
            preset_actions,
            "Sao chép",
            self.duplicate_preset,
            width=101,
            height=35,
            radius=10,
            outer_bg=PANEL,
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 6))
        RoundedButton(
            preset_actions,
            "Xóa preset",
            self.delete_preset,
            width=210,
            height=35,
            radius=10,
            outer_bg=PANEL,
            fill="#3A1D24",
            hover="#52242C",
            foreground="#FFB4AE",
            border=None,
        ).grid(row=1, column=0, columnspan=2, sticky="ew")

    def _build_workspace(self, parent: ttk.Frame) -> None:
        workspace = ttk.Frame(parent, style="App.TFrame")
        workspace.grid(row=0, column=1, sticky="nsew")
        workspace.grid_columnconfigure(0, weight=1)
        workspace.grid_rowconfigure(1, weight=1)

        filters = ttk.Frame(workspace, style="App.TFrame")
        filters.grid(row=0, column=0, sticky="ew", pady=(0, 11))
        filters.grid_columnconfigure(0, weight=1)
        self.search_entry = ttk.Entry(filters, textvariable=self.search_var)
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 9))
        self.search_entry.insert(0, "")
        self.group_combo = ttk.Combobox(filters, textvariable=self.group_var, state="readonly", width=23)
        self.group_combo.grid(row=0, column=1, padx=(0, 10))
        ttk.Checkbutton(
            filters,
            text="Chỉ phím đã gán",
            variable=self.assigned_only_var,
            style="Dark.TCheckbutton",
            command=self.refresh_table,
        ).grid(row=0, column=2)

        table_panel = RoundedPanel(workspace, outer_bg=BG, fill=PANEL, radius=18, inset=7, border=BORDER)
        table_panel.grid(row=1, column=0, sticky="nsew")
        table_frame = table_panel.content
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table_frame, columns=("group", "action", "hotkey", "state"), show="headings", selectmode="browse")
        self.tree.heading("group", text="NHÓM")
        self.tree.heading("action", text="LỆNH")
        self.tree.heading("hotkey", text="HOTKEY")
        self.tree.heading("state", text="TRẠNG THÁI")
        self.tree.column("group", width=130, minwidth=100, stretch=False)
        self.tree.column("action", width=340, minwidth=220)
        self.tree.column("hotkey", width=210, minwidth=150)
        self.tree.column("state", width=115, minwidth=100, stretch=False)
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.tag_configure("even", background=PANEL)
        self.tree.tag_configure("odd", background=ROW_ALT)
        self.tree.tag_configure("conflict", foreground="#FFAAA3")
        self.tree.tag_configure("changed", foreground="#BBAEFF")

        editor_panel = RoundedPanel(
            workspace,
            outer_bg=BG,
            fill=PANEL_2,
            radius=18,
            inset=16,
            border=BORDER,
            height=145,
        )
        editor_panel.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        editor = editor_panel.content
        editor.grid_columnconfigure(0, weight=1)
        top = ttk.Frame(editor, style="Panel2.TFrame")
        top.grid(row=0, column=0, columnspan=5, sticky="ew", pady=(0, 10))
        top.grid_columnconfigure(0, weight=1)
        tk.Label(top, textvariable=self.selection_title_var, bg=PANEL_2, fg=TEXT, font=("Segoe UI Semibold", 11)).grid(
            row=0, column=0, sticky="w"
        )
        tk.Label(top, textvariable=self.selection_meta_var, bg=PANEL_2, fg=MUTED, font=("Segoe UI", 8)).grid(
            row=1, column=0, sticky="w", pady=(2, 0)
        )

        self.hotkey_entry = ttk.Entry(editor, textvariable=self.hotkey_var, font=("Consolas", 11))
        self.hotkey_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        self.record_button = RoundedButton(
            editor,
            "Ghi tổ hợp phím",
            self.toggle_recording,
            width=142,
            outer_bg=PANEL_2,
            fill=ACCENT,
            hover=ACCENT_HOVER,
            border=None,
            foreground="#FFFFFF",
        )
        self.record_button.grid(row=1, column=1, padx=(0, 7))
        RoundedButton(
            editor,
            "Xóa gán",
            self.clear_binding,
            width=88,
            outer_bg=PANEL_2,
        ).grid(row=1, column=2, padx=(0, 7))
        RoundedButton(
            editor,
            "Khôi phục",
            self.restore_binding,
            width=96,
            outer_bg=PANEL_2,
        ).grid(row=1, column=3)
        self.conflict_label = tk.Label(
            editor,
            textvariable=self.conflict_var,
            bg=PANEL_2,
            fg=AMBER,
            font=("Segoe UI", 8),
            anchor="w",
        )
        self.conflict_label.grid(row=2, column=0, columnspan=5, sticky="ew", pady=(8, 0))

    def _bind_events(self) -> None:
        self.search_var.trace_add("write", lambda *_: self.refresh_table())
        self.group_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_table())
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Double-1>", lambda _event: self.start_recording())
        self.preset_list.bind("<<ListboxSelect>>", self.on_preset_select)
        self.preset_list.bind("<Double-1>", lambda _event: self.load_selected_preset())
        self.hotkey_entry.bind("<Return>", self.commit_manual_binding)
        self.hotkey_entry.bind("<FocusOut>", self.commit_manual_binding)
        self.root.bind_all("<KeyPress>", self.on_key_capture, add="+")
        self.root.bind("<Control-f>", lambda _event: self.search_entry.focus_set())

    def reload_document(self, force: bool = False) -> None:
        if self.document and self.document.dirty and not force:
            if not messagebox.askyesno("Tải lại file", "Các thay đổi chưa áp dụng sẽ bị bỏ. Tiếp tục?"):
                return
        try:
            self.document = HotkeyDocument.load(self.hotkey_path)
        except Exception as exc:
            self.set_status(f"Không thể đọc file: {exc}", error=True)
            messagebox.showerror("Không thể mở hotkeys.txt", str(exc))
            return

        groups: list[str] = []
        for entry in self.document.entries:
            if entry.group_label not in groups:
                groups.append(entry.group_label)
        self.group_combo["values"] = ["Tất cả nhóm", *groups]
        self.group_var.set("Tất cả nhóm")
        self.selected_entry_id = None
        self._set_editor(None)
        self.refresh_table()
        self.set_status(f"Đã đọc {len(self.document.entries)} lệnh từ {self.hotkey_path.name}")

    def refresh_table(self) -> None:
        if not self.document:
            return
        previous = self.selected_entry_id
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.iid_to_entry_id.clear()

        query = self.search_var.get().strip().casefold()
        group_filter = self.group_var.get()
        conflicts = find_conflicts(self.document.entries)
        conflict_ids = {entry_id for ids in conflicts.values() for entry_id in ids}
        shown = 0
        assigned = 0
        for index, entry in enumerate(self.document.entries):
            if entry.value:
                assigned += 1
            if group_filter != "Tất cả nhóm" and entry.group_label != group_filter:
                continue
            if self.assigned_only_var.get() and not entry.value:
                continue
            haystack = f"{entry.group_label} {entry.action} {entry.value}".casefold()
            if query and query not in haystack:
                continue

            status = "Trùng phím" if entry.entry_id in conflict_ids else ("Đã sửa" if entry.value != entry.original_value else "")
            tags = ["even" if shown % 2 == 0 else "odd"]
            if entry.entry_id in conflict_ids:
                tags.append("conflict")
            elif entry.value != entry.original_value:
                tags.append("changed")
            iid = f"entry-{index}"
            self.iid_to_entry_id[iid] = entry.entry_id
            self.tree.insert("", "end", iid=iid, values=(entry.group_label, entry.action, entry.value or "—", status), tags=tags)
            shown += 1

        self.count_var.set(f"Hiển thị {shown}/{len(self.document.entries)} · Đã gán {assigned}")
        if previous:
            matching_iid = next((iid for iid, entry_id in self.iid_to_entry_id.items() if entry_id == previous), None)
            if matching_iid:
                self.tree.selection_set(matching_iid)
                self.tree.see(matching_iid)
        self._update_dirty_status()

    def on_tree_select(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected or not self.document:
            return
        entry_id = self.iid_to_entry_id.get(selected[0])
        if not entry_id:
            return
        self.selected_entry_id = entry_id
        self._set_editor(self.document.get(entry_id))

    def _set_editor(self, entry) -> None:
        self.stop_recording()
        self._setting_editor = True
        if entry is None:
            self.selection_title_var.set("Chọn một lệnh để chỉnh sửa")
            self.selection_meta_var.set("Bạn có thể tìm theo tên lệnh hoặc hotkey.")
            self.hotkey_var.set("")
            self.conflict_var.set("")
            self.hotkey_entry.configure(state="disabled")
        else:
            suffix = f" · lựa chọn {entry.action_occurrence}" if entry.action_occurrence > 1 else ""
            self.selection_title_var.set(entry.action)
            self.selection_meta_var.set(f"{entry.group_label}{suffix}")
            self.hotkey_entry.configure(state="normal")
            self.hotkey_var.set(entry.value)
            self._update_conflict_message(entry.entry_id)
        self._setting_editor = False

    def commit_manual_binding(self, _event=None) -> None:
        if self._setting_editor or not self.document or not self.selected_entry_id:
            return
        self.document.set_value(self.selected_entry_id, self.hotkey_var.get())
        entry = self.document.get(self.selected_entry_id)
        if entry:
            self._setting_editor = True
            self.hotkey_var.set(entry.value)
            self._setting_editor = False
        self.refresh_table()
        self._update_conflict_message(self.selected_entry_id)

    def clear_binding(self) -> None:
        if not self.document or not self.selected_entry_id:
            return
        self.document.set_value(self.selected_entry_id, "")
        self.hotkey_var.set("")
        self.refresh_table()
        self._update_conflict_message(self.selected_entry_id)

    def restore_binding(self) -> None:
        if not self.document or not self.selected_entry_id:
            return
        self.document.reset_value(self.selected_entry_id)
        entry = self.document.get(self.selected_entry_id)
        self.hotkey_var.set(entry.value if entry else "")
        self.refresh_table()
        self._update_conflict_message(self.selected_entry_id)

    def toggle_recording(self) -> None:
        if self.recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self) -> None:
        if not self.selected_entry_id:
            self.set_status("Hãy chọn một lệnh trước khi ghi phím", warning=True)
            return
        self.recording = True
        self.record_button.configure(text="Đang nghe phím…")
        self.conflict_var.set("Nhấn tổ hợp phím mong muốn. Có thể dùng Ctrl, Shift và Alt.")
        self.hotkey_entry.focus_set()

    def stop_recording(self) -> None:
        if not hasattr(self, "record_button"):
            return
        self.recording = False
        self.record_button.configure(text="Ghi tổ hợp phím")

    def on_key_capture(self, event) -> str | None:
        if not self.recording or not self.document or not self.selected_entry_id:
            return None
        if event.keysym in {"Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R", "Meta_L", "Meta_R"}:
            return "break"

        hotkey = event_to_spine_hotkey(event)
        if not hotkey:
            self.set_status(f"Chưa hỗ trợ phím {event.keysym}; bạn có thể nhập tay", warning=True)
            return "break"
        self.document.set_value(self.selected_entry_id, hotkey)
        self.hotkey_var.set(hotkey)
        self.stop_recording()
        self.refresh_table()
        self._update_conflict_message(self.selected_entry_id)
        self.set_status(f"Đã ghi tổ hợp {hotkey}")
        return "break"

    def _update_conflict_message(self, entry_id: str) -> None:
        if not self.document:
            return
        entry = self.document.get(entry_id)
        if not entry or not entry.value:
            self.conflict_var.set("Chưa gán phím. Nhấn “Ghi tổ hợp phím” để nhập nhanh.")
            return
        conflicts = find_conflicts(self.document.entries)
        related_ids: list[str] = []
        for ids in conflicts.values():
            if entry_id in ids:
                related_ids = [candidate for candidate in ids if candidate != entry_id]
                break
        if related_ids:
            names = [self.document.get(candidate).action for candidate in related_ids if self.document.get(candidate)]
            self.conflict_var.set("Cảnh báo: trùng với " + ", ".join(names[:3]))
        else:
            self.conflict_var.set("Không phát hiện xung đột phím.")

    def refresh_presets(self, select_path: Path | None = None) -> None:
        PRESET_DIR.mkdir(parents=True, exist_ok=True)
        self.preset_list.delete(0, "end")
        self.preset_paths = []
        selected_index: int | None = None
        for path in sorted(PRESET_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                payload = load_preset(path)
            except Exception:
                continue
            self.preset_paths.append(path)
            self.preset_list.insert("end", payload.get("name", path.stem))
            if select_path and path.resolve() == select_path.resolve():
                selected_index = len(self.preset_paths) - 1
        if selected_index is not None:
            self.preset_list.selection_set(selected_index)
            self.preset_list.see(selected_index)
            self.on_preset_select()
        elif not self.preset_paths:
            self.preset_meta_var.set("Chưa có preset. Hãy chỉnh phím rồi lưu bộ đầu tiên.")

    def selected_preset_path(self) -> Path | None:
        selected = self.preset_list.curselection()
        if not selected or selected[0] >= len(self.preset_paths):
            return None
        return self.preset_paths[selected[0]]

    def on_preset_select(self, _event=None) -> None:
        path = self.selected_preset_path()
        if not path:
            return
        try:
            payload = load_preset(path)
            bindings = payload.get("bindings", {})
            created = str(payload.get("created_at", "")).replace("T", " ")[:19]
            self.preset_meta_var.set(f"{len(bindings)} lệnh · tạo {created}")
        except Exception as exc:
            self.preset_meta_var.set(f"Preset lỗi: {exc}")

    def create_preset(self) -> None:
        if not self.document:
            return
        name = ask_text(self.root, "Lưu preset", "Tên bộ hotkey", "Preset mới")
        if name is None:
            return
        try:
            expected = PRESET_DIR / safe_preset_filename(name)
            overwrite = expected.exists() and messagebox.askyesno("Ghi đè preset", f"Preset “{name}” đã tồn tại. Ghi đè?")
            if expected.exists() and not overwrite:
                return
            path = save_preset(PRESET_DIR, name, self.document, overwrite=overwrite)
            self.refresh_presets(path)
            self.set_status(f"Đã lưu preset “{name}”")
        except Exception as exc:
            messagebox.showerror("Không thể lưu preset", str(exc))

    def load_selected_preset(self) -> None:
        if not self.document:
            return
        path = self.selected_preset_path()
        if not path:
            self.set_status("Hãy chọn một preset", warning=True)
            return
        try:
            payload = load_preset(path)
            if payload.get("structure_fingerprint") != self.document.structure_fingerprint:
                proceed = messagebox.askyesno(
                    "Preset khác phiên bản",
                    "Cấu trúc preset khác file hotkey hiện tại. Tool chỉ nạp các lệnh khớp. Tiếp tục?",
                )
                if not proceed:
                    return
            matched, missing = apply_preset(self.document, payload)
            self.refresh_table()
            if self.selected_entry_id:
                self._set_editor(self.document.get(self.selected_entry_id))
            suffix = f", bỏ qua {missing} lệnh không khớp" if missing else ""
            self.set_status(f"Đã nạp {matched} lệnh từ preset{suffix}")
        except Exception as exc:
            messagebox.showerror("Không thể nạp preset", str(exc))

    def rename_preset(self) -> None:
        path = self.selected_preset_path()
        if not path:
            self.set_status("Hãy chọn một preset để đổi tên", warning=True)
            return
        try:
            payload = load_preset(path)
            old_name = payload.get("name", path.stem)
            new_name = ask_text(self.root, "Đổi tên preset", "Tên mới", old_name)
            if new_name is None or new_name.strip() == old_name:
                return
            new_path = PRESET_DIR / safe_preset_filename(new_name)
            if new_path.exists() and new_path.resolve() != path.resolve():
                raise FileExistsError(f"Preset “{new_name}” đã tồn tại.")
            payload["name"] = new_name.strip()
            new_path.write_text(__import__("json").dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if new_path.resolve() != path.resolve():
                path.unlink()
            self.refresh_presets(new_path)
            self.set_status(f"Đã đổi tên preset thành “{new_name}”")
        except Exception as exc:
            messagebox.showerror("Không thể đổi tên", str(exc))

    def duplicate_preset(self) -> None:
        path = self.selected_preset_path()
        if not path:
            self.set_status("Hãy chọn một preset để nhân bản", warning=True)
            return
        try:
            payload = load_preset(path)
            new_name = ask_text(self.root, "Nhân bản preset", "Tên bản sao", f"{payload.get('name', path.stem)} - Copy")
            if new_name is None:
                return
            new_path = PRESET_DIR / safe_preset_filename(new_name)
            if new_path.exists():
                raise FileExistsError(f"Preset “{new_name}” đã tồn tại.")
            payload["name"] = new_name.strip()
            new_path.write_text(__import__("json").dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.refresh_presets(new_path)
            self.set_status(f"Đã tạo bản sao “{new_name}”")
        except Exception as exc:
            messagebox.showerror("Không thể nhân bản", str(exc))

    def delete_preset(self) -> None:
        path = self.selected_preset_path()
        if not path:
            self.set_status("Hãy chọn một preset để xóa", warning=True)
            return
        try:
            payload = load_preset(path)
            name = payload.get("name", path.stem)
            if not messagebox.askyesno("Xóa preset", f"Xóa preset “{name}”? Thao tác này không ảnh hưởng hotkeys.txt."):
                return
            path.unlink()
            self.refresh_presets()
            self.set_status(f"Đã xóa preset “{name}”")
        except Exception as exc:
            messagebox.showerror("Không thể xóa preset", str(exc))

    def apply_to_spine(self) -> None:
        if not self.document:
            return
        self.commit_manual_binding()
        if not self.document.dirty:
            self.set_status("Không có thay đổi để áp dụng", warning=True)
            return
        if is_spine_running():
            messagebox.showwarning(
                "Hãy đóng Spine",
                "Spine đang chạy và có thể ghi đè hotkeys.txt khi thoát. Hãy đóng Spine hoàn toàn rồi bấm Áp dụng lại.",
            )
            self.set_status("Chưa áp dụng: Spine vẫn đang chạy", warning=True)
            return
        if self.document.changed_on_disk():
            messagebox.showwarning(
                "File đã thay đổi",
                "hotkeys.txt vừa bị chương trình khác thay đổi. Tool sẽ tải lại để tránh ghi đè dữ liệu mới.",
            )
            self.reload_document(force=True)
            return
        conflicts = find_conflicts(self.document.entries)
        if conflicts:
            proceed = messagebox.askyesno(
                "Có hotkey trùng",
                f"Đang có {len(conflicts)} tổ hợp phím bị trùng. Vẫn áp dụng vào Spine?",
            )
            if not proceed:
                return
        try:
            backup = self.document.save_atomic(BACKUP_DIR)
            self.refresh_table()
            self.set_status(f"Đã áp dụng thành công · backup: {backup.name}")
            messagebox.showinfo("Đã áp dụng", "File hotkeys.txt đã được cập nhật an toàn. Bạn có thể mở lại Spine.")
        except Exception as exc:
            self.set_status(f"Áp dụng thất bại: {exc}", error=True)
            messagebox.showerror("Không thể áp dụng", str(exc))

    def _update_dirty_status(self) -> None:
        if self.document and self.document.dirty:
            changed = sum(entry.value != entry.original_value for entry in self.document.entries)
            self.status_dot.configure(fg=AMBER)
            self.status_var.set(f"{changed} thay đổi chưa áp dụng")
        elif self.document:
            self.status_dot.configure(fg=GREEN)

    def set_status(self, text: str, error: bool = False, warning: bool = False) -> None:
        self.status_var.set(text)
        self.status_dot.configure(fg=RED if error else AMBER if warning else GREEN)

    def on_close(self) -> None:
        if self.document and self.document.dirty:
            if not messagebox.askyesno("Thoát Hotkey Studio", "Bạn còn thay đổi chưa áp dụng. Thoát và bỏ các thay đổi này?"):
                return
        self.root.destroy()


def event_to_spine_hotkey(event) -> str:
    key_map = {
        "Return": "ENTER",
        "KP_Enter": "NUMPAD_ENTER",
        "Escape": "ESCAPE",
        "BackSpace": "BACKSPACE",
        "Delete": "DELETE",
        "Tab": "TAB",
        "space": "SPACE",
        "Home": "HOME",
        "End": "END",
        "Prior": "PAGE_UP",
        "Next": "PAGE_DOWN",
        "Up": "UP",
        "Down": "DOWN",
        "Left": "LEFT",
        "Right": "RIGHT",
        "Insert": "INSERT",
        "bracketleft": "LEFT_BRACKET",
        "bracketright": "RIGHT_BRACKET",
        "slash": "SLASH",
        "backslash": "BACKSLASH",
        "comma": "COMMA",
        "period": "PERIOD",
        "minus": "MINUS",
        "equal": "EQUALS",
        "plus": "PLUS",
        "KP_Add": "NUMPAD_PLUS",
        "KP_Subtract": "NUMPAD_MINUS",
        "KP_Multiply": "NUMPAD_MULTIPLY",
        "KP_Divide": "NUMPAD_DIVIDE",
        "KP_Decimal": "NUMPAD_DECIMAL",
    }
    punctuation = {
        "semicolon": "';'",
        "colon": "':'",
        "apostrophe": "'''",
        "quotedbl": "'\"'",
        "grave": "'`'",
        "asciitilde": "'~'",
    }
    keysym = event.keysym
    if keysym in key_map:
        base = key_map[keysym]
    elif keysym in punctuation:
        base = punctuation[keysym]
    elif keysym.startswith("F") and keysym[1:].isdigit():
        base = keysym.upper()
    elif keysym.startswith("KP_") and keysym[3:].isdigit():
        base = f"NUMPAD_{keysym[3:]}"
    elif len(keysym) == 1 and keysym.isalnum():
        base = keysym.upper()
    else:
        return ""

    modifiers: list[str] = []
    state = int(event.state)
    if state & 0x4:
        modifiers.append("ctrl")
    if state & 0x1:
        modifiers.append("shift")
    # Trên Windows, Tk dùng 0x20000 cho Alt. Bit 0x8 có thể là Num Lock,
    # vì vậy không được coi 0x8 là Alt trên nền tảng này.
    alt_pressed = bool(state & 0x20000) if sys.platform == "win32" else bool(state & 0x8)
    if alt_pressed:
        modifiers.append("alt")
    return " + ".join([*modifiers, base])


def is_spine_running() -> bool:
    if sys.platform != "win32":
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
            timeout=4,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for row in csv.reader(result.stdout.splitlines()):
            if not row:
                continue
            process_name = row[0].casefold()
            if process_name == "spine.exe" or (process_name.startswith("spine-") and process_name.endswith(".exe")):
                return True
    except Exception:
        return False
    return False


def ask_text(parent: tk.Tk, title: str, label: str, initial: str = "") -> str | None:
    result: dict[str, str | None] = {"value": None}
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.configure(bg=PANEL)
    dialog.resizable(False, False)
    dialog.transient(parent)
    dialog.grab_set()

    frame = tk.Frame(dialog, bg=PANEL, padx=22, pady=20)
    frame.pack(fill="both", expand=True)
    tk.Label(frame, text=title, bg=PANEL, fg=TEXT, font=("Segoe UI Semibold", 14)).pack(anchor="w")
    tk.Label(frame, text=label, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(14, 6))
    value_var = tk.StringVar(value=initial)
    entry = ttk.Entry(frame, textvariable=value_var, width=42)
    entry.pack(fill="x")
    error_var = tk.StringVar()
    tk.Label(frame, textvariable=error_var, bg=PANEL, fg=RED, font=("Segoe UI", 8)).pack(anchor="w", pady=(5, 0))
    buttons = tk.Frame(frame, bg=PANEL)
    buttons.pack(fill="x", pady=(16, 0))

    def accept(_event=None) -> None:
        value = value_var.get().strip()
        if not value:
            error_var.set("Tên không được để trống.")
            return
        result["value"] = value
        dialog.destroy()

    def cancel(_event=None) -> None:
        dialog.destroy()

    ttk.Button(buttons, text="Lưu", style="Primary.TButton", command=accept).pack(side="right")
    ttk.Button(buttons, text="Hủy", style="Secondary.TButton", command=cancel).pack(side="right", padx=(0, 8))
    dialog.bind("<Return>", accept)
    dialog.bind("<Escape>", cancel)
    dialog.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - dialog.winfo_reqwidth()) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - dialog.winfo_reqheight()) // 2
    dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
    entry.focus_set()
    entry.selection_range(0, "end")
    parent.wait_window(dialog)
    return result["value"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Giao diện quản lý hotkey và preset cho Spine.")
    parser.add_argument("--file", type=Path, default=DEFAULT_HOTKEY_FILE, help="Đường dẫn tới hotkeys.txt")
    args = parser.parse_args()
    root = tk.Tk()
    HotkeyStudio(root, args.file)
    root.mainloop()


if __name__ == "__main__":
    main()
