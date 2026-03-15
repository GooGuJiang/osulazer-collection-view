from __future__ import annotations

import ctypes
import json
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps, ImageTk

from .cover_cache import CoverCache
from .extractor import REALM_FILENAME, RealmExtractor, detect_realm_file
from .exporter import export_current_view
from .models import BeatmapEntry, CollectionInfo, ExtractedData

MODE_DEFINITIONS = (
    ("osu", "osu", "osu.png"),
    ("taiko", "taiko", "taiko.png"),
    ("ctb", "fruits", "ctb.png"),
    ("mania", "mania", "mania.png"),
)

COLUMN_DEFINITIONS = (
    ("name_original", "名称（原语言）", True, 320, tk.W),
    ("star_rating", "难度", True, 70, tk.CENTER),
    ("bid", "BID", True, 80, tk.CENTER),
    ("artist", "艺术家（原语言）", True, 180, tk.W),
    ("difficulty_name", "难度名", True, 180, tk.W),
    ("mapper", "谱师", True, 140, tk.W),
    ("mode", "模式", True, 70, tk.CENTER),
    ("sid", "SID", False, 80, tk.CENTER),
    ("cs", "CS", False, 60, tk.CENTER),
    ("od", "OD", False, 60, tk.CENTER),
    ("ar", "AR", False, 60, tk.CENTER),
    ("hp", "HP", False, 60, tk.CENTER),
    ("note_count", "Note数", False, 80, tk.CENTER),
    ("length", "长度", False, 80, tk.CENTER),
    ("bpm", "BPM", False, 80, tk.CENTER),
    ("status", "状态", False, 90, tk.CENTER),
    ("name", "名称", False, 320, tk.W),
    ("md5", "MD5", False, 280, tk.W),
)

DEFAULT_COLUMN_VISIBILITY = {key: default for key, _, default, _, _ in COLUMN_DEFINITIONS}
DEFAULT_COLUMN_ORDER = [key for key, _, _, _, _ in COLUMN_DEFINITIONS]

class CollectionViewApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        source_dir = Path(__file__).resolve().parent.parent
        self.resource_dir = Path(getattr(sys, "_MEIPASS", source_dir)).resolve()
        self.base_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else source_dir
        self.runtime_dir = self.base_dir / "runtime"
        self.cover_dir = self.runtime_dir / "covers"
        self.mode_assets_dir = self.resource_dir / "assets" / "modes"
        self.icon_assets_dir = self.resource_dir / "assets" / "icons"
        self.logo_png_path = self.resource_dir / "assets" / "logo.png"
        self.logo_ico_path = self.resource_dir / "assets" / "logo.ico"
        self.settings_path = self.runtime_dir / "ui_settings.json"

        self.extractor = RealmExtractor(self.base_dir, self.runtime_dir, resource_dir=self.resource_dir)
        self.cover_cache = CoverCache(self.cover_dir)

        self.data: ExtractedData | None = None
        self.collections: list[CollectionInfo] = []
        self.selected_collection: CollectionInfo | None = None
        self.selected_mode = "osu"
        self.detected_realm: Path | None = None
        self.mode_photos: dict[str, ImageTk.PhotoImage] = {}
        self.mode_buttons: dict[str, tk.Button] = {}
        self.cover_load_limiter = threading.Semaphore(4)
        self.detail_popup: tk.Toplevel | None = None
        self.settings_popup: tk.Toplevel | None = None
        self.settings_icon_photo: ImageTk.PhotoImage | None = None
        self.app_icon_photo: tk.PhotoImage | None = None
        self.icon_handles: list[int] = []
        self.selected_item = None
        self.displayed_items: list[BeatmapEntry] = []
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.preview_cover_path: Path | None = None
        self.preview_request_id = 0
        self.preview_resize_job: str | None = None
        self.sort_column: str | None = None
        self.sort_descending = False
        self.dragged_heading_column: str | None = None
        self.dragged_heading_active = False
        self.drag_start_x = 0
        self.suppress_next_heading_sort = False
        self.settings_payload = self._load_settings_payload()
        self.column_visibility = self._load_column_visibility(self.settings_payload)
        self.column_order = self._load_column_order(self.settings_payload)
        self.column_vars = {
            key: tk.BooleanVar(value=self.column_visibility.get(key, default))
            for key, _, default, _, _ in COLUMN_DEFINITIONS
        }

        self.status_var = tk.StringVar(value="")
        self.collection_summary_var = tk.StringVar(value="尚未加载数据。")
        self.item_summary_var = tk.StringVar(value="")

        self._build_ui()
        self._configure_app_icon()
        self._load_mode_icons()
        self._load_settings_icon()
        self._refresh_detected_realm()
        self._apply_mode_button_styles()
        self._apply_column_visibility()
        self._update_export_state()

    def _build_ui(self) -> None:
        self.root.title("osu! 收藏夹查看器")
        self.root.geometry("1540x940")
        self.root.minsize(1280, 800)

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Section.TLabel", font=("Segoe UI", 13, "bold"))
        style.configure("Muted.TLabel", foreground="#666666")
        style.configure("Status.TLabel", foreground="#1f4f82")
        style.configure("PopupTitle.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("PopupField.TLabel", foreground="#64748b", font=("Segoe UI", 9))
        style.configure("PopupValue.TLabel", font=("Segoe UI", 10))
        style.configure("Treeview", font=("Segoe UI", 9), rowheight=22)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

        container = ttk.Frame(self.root, padding=10)
        container.pack(fill=tk.BOTH, expand=True)

        top_bar = ttk.Frame(container)
        top_bar.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(
            top_bar,
            textvariable=self.status_var,
            style="Status.TLabel",
            wraplength=980,
            justify=tk.LEFT,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        actions = ttk.Frame(top_bar)
        actions.pack(side=tk.RIGHT)
        ttk.Button(actions, text="刷新检测", command=self._refresh_detected_realm).pack(side=tk.LEFT, padx=(0, 8))
        self.load_button = ttk.Button(actions, text="加载", command=self._load_realm)
        self.load_button.pack(side=tk.LEFT)
        self.export_button = ttk.Button(actions, text="导出", command=self._export_current_view)
        self.export_button.pack(side=tk.LEFT, padx=(8, 0))

        panes = ttk.Panedwindow(container, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True)
        self.main_panes = panes

        left_panel = ttk.Frame(panes, padding=6, width=270)
        right_panel = ttk.Frame(panes, padding=6)
        self.left_panel = left_panel
        panes.add(left_panel, weight=1)
        panes.add(right_panel, weight=6)

        self._build_collection_panel(left_panel)
        self._build_detail_panel(right_panel)
        self.root.after(0, self._reset_main_pane_layout)

    def _configure_app_icon(self) -> None:
        self._apply_window_icon(self.root)

    def _apply_window_icon(self, window: tk.Misc) -> None:
        if self.logo_ico_path.exists():
            try:
                window.iconbitmap(str(self.logo_ico_path))
            except Exception:  # noqa: BLE001
                pass

        if not self.logo_png_path.exists():
            self._apply_native_window_icon(window)
            return

        try:
            if self.app_icon_photo is None:
                self.app_icon_photo = tk.PhotoImage(file=str(self.logo_png_path))
            window.iconphoto(True, self.app_icon_photo)
        except Exception:  # noqa: BLE001
            pass

        self._apply_native_window_icon(window)

    def _apply_native_window_icon(self, window: tk.Misc) -> None:
        if not self.logo_ico_path.exists():
            return
        window.after(0, lambda target=window: self._set_native_window_icon(target))

    def _set_native_window_icon(self, window: tk.Misc) -> None:
        if not hasattr(ctypes, "windll"):
            return
        try:
            if not window.winfo_exists():
                return
            hwnd = window.winfo_id()
            user32 = ctypes.windll.user32
            image_icon = 1
            lr_loadfromfile = 0x0010
            wm_seticon = 0x0080
            icon_small = 0
            icon_big = 1
            gclp_hicon = -14
            gclp_hiconsm = -34
            sm_cxicon = 11
            sm_cyicon = 12
            sm_cxsmicon = 49
            sm_cysmicon = 50

            large_icon = user32.LoadImageW(
                None,
                str(self.logo_ico_path),
                image_icon,
                user32.GetSystemMetrics(sm_cxicon),
                user32.GetSystemMetrics(sm_cyicon),
                lr_loadfromfile,
            )
            small_icon = user32.LoadImageW(
                None,
                str(self.logo_ico_path),
                image_icon,
                user32.GetSystemMetrics(sm_cxsmicon),
                user32.GetSystemMetrics(sm_cysmicon),
                lr_loadfromfile,
            )

            if large_icon:
                user32.SendMessageW(hwnd, wm_seticon, icon_big, large_icon)
                self._set_window_class_icon(hwnd, gclp_hicon, large_icon)
                self.icon_handles.append(int(large_icon))
            if small_icon:
                user32.SendMessageW(hwnd, wm_seticon, icon_small, small_icon)
                self._set_window_class_icon(hwnd, gclp_hiconsm, small_icon)
                self.icon_handles.append(int(small_icon))
        except Exception:  # noqa: BLE001
            pass

    def _set_window_class_icon(self, hwnd: int, index: int, icon_handle: int) -> None:
        if not hasattr(ctypes, "windll"):
            return
        try:
            user32 = ctypes.windll.user32
            if hasattr(user32, "SetClassLongPtrW"):
                user32.SetClassLongPtrW(hwnd, index, icon_handle)
            else:
                user32.SetClassLongW(hwnd, index, icon_handle)
        except Exception:  # noqa: BLE001
            pass

    def _build_collection_panel(self, parent: ttk.Frame) -> None:
        header_row = ttk.Frame(parent)
        header_row.pack(fill=tk.X)

        ttk.Label(header_row, text="收藏夹列表", style="Section.TLabel").pack(side=tk.LEFT, anchor=tk.W)

        mode_row = ttk.Frame(header_row)
        mode_row.pack(side=tk.LEFT, padx=(12, 0))
        for label, _, _ in MODE_DEFINITIONS:
            button = tk.Button(
                mode_row,
                text=label.upper() if label != "ctb" else "CTB",
                compound=tk.LEFT,
                relief=tk.SOLID,
                borderwidth=1,
                command=lambda value=label: self._set_mode(value),
                bg="#f8fafc",
                activebackground="#dbeafe",
                font=("Segoe UI", 9, "bold"),
                cursor="hand2",
                padx=7,
                pady=4,
            )
            button.pack(side=tk.LEFT, padx=(0, 6))
            self.mode_buttons[label] = button

        ttk.Label(parent, textvariable=self.collection_summary_var, style="Muted.TLabel").pack(anchor=tk.W, pady=(4, 6))

        tree_holder = ttk.Frame(parent, height=470)
        tree_holder.pack(fill=tk.X, expand=False)
        tree_holder.pack_propagate(False)

        tree_frame = ttk.Frame(tree_holder)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("name", "total", "visible")
        self.collection_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        self.collection_tree.heading("name", text="收藏夹")
        self.collection_tree.heading("total", text="总数")
        self.collection_tree.heading("visible", text="当前模式")
        self.collection_tree.column("name", width=180, anchor=tk.W)
        self.collection_tree.column("total", width=48, anchor=tk.CENTER)
        self.collection_tree.column("visible", width=58, anchor=tk.CENTER)
        self.collection_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.collection_tree.bind("<<TreeviewSelect>>", self._on_collection_selected)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.collection_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.collection_tree.configure(yscrollcommand=scrollbar.set)

        preview_frame = ttk.LabelFrame(parent, text="背景图展示", padding=6, height=150)
        preview_frame.pack(fill=tk.X, expand=False, pady=(8, 0))
        preview_frame.pack_propagate(False)
        self.preview_label = ttk.Label(
            preview_frame,
            text="选择谱面后在这里显示背景图",
            anchor=tk.CENTER,
            justify=tk.CENTER,
            wraplength=220,
        )
        self.preview_label.pack(fill=tk.BOTH, expand=True)
        self.preview_label.bind("<Configure>", self._on_preview_configure)

    def _build_detail_panel(self, parent: ttk.Frame) -> None:
        title_row = ttk.Frame(parent)
        title_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(title_row, text="谱面列表", style="Section.TLabel").pack(side=tk.LEFT)
        self.settings_button = tk.Button(
            title_row,
            text="设置",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            borderwidth=0,
            cursor="hand2",
            command=self._open_settings_popup,
            bg="#eff6ff",
            activebackground="#dbeafe",
            padx=7,
            pady=4,
        )
        self.settings_button.pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(parent, textvariable=self.item_summary_var, style="Muted.TLabel").pack(anchor=tk.W, pady=(0, 8))

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True)

        table_frame = ttk.Frame(list_frame)
        table_frame.pack(fill=tk.BOTH, expand=True)

        all_columns = [key for key, *_ in COLUMN_DEFINITIONS]
        self.beatmap_tree = ttk.Treeview(table_frame, columns=all_columns, show="headings", selectmode="browse")
        for key, header, _, width, anchor in COLUMN_DEFINITIONS:
            self.beatmap_tree.heading(key, text=header, command=lambda value=key: self._toggle_beatmap_sort(value))
            self.beatmap_tree.column(key, width=width, anchor=anchor)
        self.beatmap_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.beatmap_tree.bind("<<TreeviewSelect>>", self._on_beatmap_selected)
        self.beatmap_tree.bind("<Double-1>", self._on_beatmap_double_clicked)
        self.beatmap_tree.bind("<ButtonPress-1>", self._on_beatmap_tree_button_press, add="+")
        self.beatmap_tree.bind("<B1-Motion>", self._on_beatmap_tree_drag, add="+")
        self.beatmap_tree.bind("<ButtonRelease-1>", self._on_beatmap_tree_button_release, add="+")

        self.beatmap_scrollbar = tk.Scrollbar(
            table_frame,
            orient=tk.VERTICAL,
            command=self.beatmap_tree.yview,
            width=14,
            relief=tk.FLAT,
            activebackground="#cbd5e1",
            bg="#e5e7eb",
            troughcolor="#f8fafc",
            highlightthickness=0,
            bd=0,
        )
        self.beatmap_scrollbar.place(relx=1.0, x=-2, y=2, relheight=1.0, height=-4, anchor="ne")
        self.beatmap_tree.configure(yscrollcommand=self.beatmap_scrollbar.set)

    def _reset_main_pane_layout(self) -> None:
        total_width = self.main_panes.winfo_width()
        if total_width <= 0:
            self.root.after(50, self._reset_main_pane_layout)
            return

        requested = max(self.left_panel.winfo_reqwidth() + 18, 300)
        left_width = min(requested, max(total_width - 760, 300))
        self.main_panes.sashpos(0, left_width)

    def _load_mode_icons(self) -> None:
        for label, _, filename in MODE_DEFINITIONS:
            image_path = self.mode_assets_dir / filename
            if not image_path.exists():
                continue
            image = Image.open(image_path).convert("RGBA")
            image = image.resize((18, 18), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            self.mode_photos[label] = photo
            self.mode_buttons[label].configure(image=photo)

    def _load_settings_icon(self) -> None:
        image_path = self.icon_assets_dir / "settings.png"
        if not image_path.exists():
            return
        image = Image.open(image_path).convert("RGBA")
        image = image.resize((18, 18), Image.Resampling.LANCZOS)
        self.settings_icon_photo = ImageTk.PhotoImage(image)
        self.settings_button.configure(image=self.settings_icon_photo, text="")

    def _open_settings_popup(self) -> None:
        if self.settings_popup and self.settings_popup.winfo_exists():
            self.settings_popup.deiconify()
            self.settings_popup.lift()
            self.settings_popup.focus_force()
            self._position_settings_popup(self.settings_popup)
            return

        popup = tk.Toplevel(self.root)
        popup.title("列表设置")
        popup.transient(self.root)
        popup.resizable(False, False)
        popup.configure(padx=12, pady=12)
        popup.protocol("WM_DELETE_WINDOW", popup.destroy)
        self.settings_popup = popup
        self._apply_window_icon(popup)

        ttk.Label(popup, text="谱面列表显示列", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(popup, text="勾选后立即生效。", style="Muted.TLabel").grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(2, 8),
        )
        for index, (key, header, _, _, _) in enumerate(COLUMN_DEFINITIONS):
            row = index // 3 + 2
            column = index % 3
            check = tk.Checkbutton(
                popup,
                text=header,
                variable=self.column_vars[key],
                command=self._on_column_setting_changed,
                anchor="w",
                padx=4,
                pady=2,
                selectcolor="white",
                font=("Segoe UI", 10),
            )
            check.grid(row=row, column=column, sticky="w", padx=(0, 18), pady=2)
        button_row = len(COLUMN_DEFINITIONS) // 3 + 3
        ttk.Button(popup, text="恢复默认列设置", command=self._reset_column_settings).grid(
            row=button_row,
            column=0,
            sticky="w",
            pady=(10, 0),
        )
        ttk.Button(popup, text="关闭", command=popup.destroy).grid(row=button_row, column=2, sticky="e", pady=(10, 0))

        self._position_settings_popup(popup)

    def _position_settings_popup(self, popup: tk.Toplevel) -> None:
        popup.update_idletasks()
        self.root.update_idletasks()
        button_x = self.settings_button.winfo_rootx()
        button_y = self.settings_button.winfo_rooty()
        button_height = self.settings_button.winfo_height()
        popup_width = popup.winfo_width()
        popup_height = popup.winfo_height()
        root_right = self.root.winfo_rootx() + self.root.winfo_width()
        root_bottom = self.root.winfo_rooty() + self.root.winfo_height()

        x = button_x + self.settings_button.winfo_width() - popup_width
        y = button_y + button_height + 6
        if x + popup_width > root_right - 12:
            x = root_right - popup_width - 12
        if y + popup_height > root_bottom - 12:
            y = button_y - popup_height - 6
        popup.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _load_settings_payload(self) -> dict[str, object]:
        if not self.settings_path.exists():
            return {}
        try:
            payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
        return payload if isinstance(payload, dict) else {}

    def _load_column_visibility(self, payload: dict[str, object] | None = None) -> dict[str, bool]:
        defaults = dict(DEFAULT_COLUMN_VISIBILITY)
        payload = payload or {}
        stored = payload.get("visibleColumns", {})
        if not isinstance(stored, dict):
            return defaults
        for key in defaults:
            if key in stored:
                defaults[key] = bool(stored[key])
        return defaults

    def _load_column_order(self, payload: dict[str, object] | None = None) -> list[str]:
        defaults = list(DEFAULT_COLUMN_ORDER)
        payload = payload or {}
        stored = payload.get("columnOrder", [])
        if not isinstance(stored, list):
            return defaults

        seen = set()
        ordered_keys = []
        for key in stored:
            if key in defaults and key not in seen:
                ordered_keys.append(key)
                seen.add(key)
        for key in defaults:
            if key not in seen:
                ordered_keys.append(key)
        return ordered_keys

    def _save_column_visibility(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "visibleColumns": {key: var.get() for key, var in self.column_vars.items()},
            "columnOrder": list(self.column_order),
        }
        self.settings_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _visible_column_keys(self) -> list[str]:
        keys = [key for key in self.column_order if self.column_vars[key].get()]
        return keys or ["name_original"]

    def _apply_column_visibility(self) -> None:
        self.beatmap_tree.configure(displaycolumns=self._visible_column_keys())
        self._refresh_beatmap_headings()

    def _on_column_setting_changed(self) -> None:
        self._save_column_visibility()
        if self.sort_column and not self.column_vars[self.sort_column].get():
            self.sort_column = None
            self.sort_descending = False
        self._apply_column_visibility()
        self._refresh_beatmap_rows()

    def _reset_column_settings(self) -> None:
        self.column_order = list(DEFAULT_COLUMN_ORDER)
        for key, var in self.column_vars.items():
            var.set(DEFAULT_COLUMN_VISIBILITY[key])
        self._save_column_visibility()
        if self.sort_column and not self.column_vars[self.sort_column].get():
            self.sort_column = None
            self.sort_descending = False
        self._apply_column_visibility()
        self._refresh_beatmap_rows()

    def _export_current_view(self) -> None:
        if not self.selected_collection:
            messagebox.showinfo("无法导出", "请先选择一个收藏夹。")
            return

        items = list(self.displayed_items)
        if not items:
            messagebox.showinfo("无法导出", "当前没有可导出的谱面列表。")
            return

        visible_keys = self._current_displayed_column_keys()
        headers = [self.beatmap_tree.heading(key, option="text") for key in visible_keys]
        rows = []
        for item in items:
            row_values = self._row_values_for_item(item)
            rows.append([row_values[key] for key in visible_keys])

        default_name = f"{self.selected_collection.name}_{self.selected_mode}.xlsx".replace("/", "_").replace("\\", "_")
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="导出当前列表",
            defaultextension=".xlsx",
            filetypes=[("Excel 文件", "*.xlsx")],
            initialfile=default_name,
        )
        if not path:
            return

        try:
            export_current_view(
                Path(path),
                sheet_name=self.selected_collection.name,
                headers=headers,
                rows=rows,
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("导出失败", str(exc))
            return

        messagebox.showinfo("导出成功", f"已导出到：{path}")

    def _current_displayed_column_keys(self) -> list[str]:
        display_columns = self.beatmap_tree.cget("displaycolumns")
        if display_columns == "#all":
            return list(self.beatmap_tree.cget("columns"))
        return list(display_columns)

    def _refresh_detected_realm(self) -> None:
        self.detected_realm = detect_realm_file(self.base_dir)
        if self.detected_realm:
            self.status_var.set(
                f"请将 {REALM_FILENAME} 手动复制到当前文件夹：{self.base_dir}；当前状态：已检测到 {REALM_FILENAME}，可以点击“加载”开始解析。"
            )
            self.load_button.configure(state=tk.NORMAL)
        else:
            self.status_var.set(
                f"请将 {REALM_FILENAME} 手动复制到当前文件夹：{self.base_dir}；当前状态：未检测到可用数据库。"
            )
            self.load_button.configure(state=tk.DISABLED)

    def _set_mode(self, mode: str) -> None:
        self.selected_mode = mode
        self._apply_mode_button_styles()
        self._refresh_collections()

    def _apply_mode_button_styles(self) -> None:
        for mode, button in self.mode_buttons.items():
            selected = mode == self.selected_mode
            button.configure(
                bg="#dbeafe" if selected else "#f3f4f6",
                activebackground="#bfdbfe" if selected else "#e5e7eb",
                fg="#0f172a",
                relief=tk.SOLID,
                bd=2 if selected else 1,
            )

    def _update_load_state(self, is_loading: bool) -> None:
        if is_loading:
            self.load_button.configure(state=tk.DISABLED)
            self.export_button.configure(state=tk.DISABLED)
        else:
            self.load_button.configure(state=tk.NORMAL if self.detected_realm else tk.DISABLED)
            self._update_export_state()

    def _update_export_state(self) -> None:
        has_items = bool(self.selected_collection and self.selected_collection.items_for_mode(self.selected_mode))
        self.export_button.configure(state=tk.NORMAL if has_items else tk.DISABLED)

    def _load_realm(self) -> None:
        if not self.detected_realm:
            messagebox.showwarning("未检测到数据库", f"请先把 {REALM_FILENAME} 复制到当前目录。")
            return

        self._update_load_state(is_loading=True)
        self.status_var.set(
            f"请将 {REALM_FILENAME} 手动复制到当前文件夹：{self.base_dir}；当前状态：正在读取 realm，请稍候。"
        )
        realm_path = self.detected_realm

        def worker() -> None:
            try:
                extracted = self.extractor.extract(realm_path)
            except Exception as exc:  # noqa: BLE001
                error_text = str(exc)
                self.root.after(0, lambda message=error_text: self._on_load_failed(message))
                return

            self.root.after(0, lambda data=extracted, path=realm_path: self._on_load_completed(data, path))

        threading.Thread(target=worker, daemon=True).start()

    def _on_load_failed(self, error_text: str) -> None:
        self._update_load_state(is_loading=False)
        self._refresh_detected_realm()
        messagebox.showerror("加载失败", error_text)

    def _on_load_completed(self, extracted: ExtractedData, realm_path: Path) -> None:
        self.data = extracted
        self.collections = extracted.collections
        self.selected_collection = None
        self._update_load_state(is_loading=False)
        self.status_var.set(
            f"请将 {REALM_FILENAME} 手动复制到当前文件夹：{self.base_dir}；当前状态：加载完成，当前读取 {realm_path.name}。"
        )
        self._refresh_collections()

    def _collections_for_current_mode(self) -> list[CollectionInfo]:
        return [collection for collection in self.collections if collection.items_for_mode(self.selected_mode)]

    def _refresh_collections(self) -> None:
        visible_collections = self._collections_for_current_mode()
        self.collection_tree.delete(*self.collection_tree.get_children())

        for index, collection in enumerate(visible_collections):
            mode_items = collection.items_for_mode(self.selected_mode)
            self.collection_tree.insert(
                "",
                tk.END,
                iid=f"collection-{index}",
                values=(
                    collection.name,
                    collection.total_count,
                    len(mode_items),
                ),
            )

        self.collection_summary_var.set(
            f"当前模式: {self.selected_mode} | 收藏夹数: {len(visible_collections)} / {len(self.collections)}"
        )

        self.selected_collection = visible_collections[0] if visible_collections else None
        if self.selected_collection:
            self.collection_tree.selection_set("collection-0")
            self.collection_tree.focus("collection-0")
            self._refresh_beatmap_rows(select_first=True)
        else:
            self.selected_item = None
            self.displayed_items = []
            self._clear_preview()
            self._refresh_beatmap_rows()
        self._update_export_state()

    def _refresh_beatmap_rows(self, select_first: bool = False) -> None:
        self.beatmap_tree.delete(*self.beatmap_tree.get_children())

        if not self.selected_collection:
            self.displayed_items = []
            self.item_summary_var.set("")
            self._update_export_state()
            return

        source_items = self.selected_collection.items_for_mode(self.selected_mode)
        items = self._sorted_beatmap_items(source_items)
        self.displayed_items = items
        self.item_summary_var.set(
            f"收藏夹: {self.selected_collection.name} | 显示 {len(items)} 项 | 缺失 {sum(1 for item in items if item.missing)} 项"
        )

        if not items:
            self.selected_item = None
            self._clear_preview()
            self._update_export_state()
            return

        if select_first or self.selected_item not in items:
            self.selected_item = items[0]

        for index, item in enumerate(items):
            row_values = self._row_values_for_item(item)
            tags = ("missing",) if item.missing else ()
            self.beatmap_tree.insert(
                "",
                tk.END,
                iid=f"beatmap-{index}",
                values=[row_values[column] for column in self.beatmap_tree["columns"]],
                tags=tags,
            )
        self.beatmap_tree.tag_configure("missing", foreground="#9f1239")
        self._apply_column_visibility()

        if select_first:
            self.beatmap_tree.selection_set("beatmap-0")
            self.beatmap_tree.focus("beatmap-0")
        selected_index = items.index(self.selected_item) if self.selected_item in items else 0
        target_iid = f"beatmap-{selected_index}"
        self.beatmap_tree.selection_set(target_iid)
        self.beatmap_tree.focus(target_iid)
        self._center_beatmap_row(target_iid, selected_index, len(items))
        self._load_preview_for_item(self.selected_item)
        self._update_export_state()

    def _on_collection_selected(self, _event=None) -> None:
        selected = self.collection_tree.selection()
        if not selected:
            return
        index = int(selected[0].split("-")[-1])
        visible_collections = self._collections_for_current_mode()
        if index < len(visible_collections):
            self.selected_collection = visible_collections[index]
            self.selected_item = None
            self._refresh_beatmap_rows(select_first=True)

    def _row_values_for_item(self, item) -> dict[str, str]:
        return {
            "name_original": item.name_original,
            "star_rating": item.star_rating_text or "-",
            "bid": item.bid_text or "-",
            "sid": item.sid_text or "-",
            "difficulty_name": item.difficulty_name or "-",
            "mapper": item.mapper or "-",
            "mode": item.mode,
            "cs": item.cs_text or "-",
            "od": item.od_text or "-",
            "ar": item.ar_text or "-",
            "hp": item.hp_text or "-",
            "note_count": item.note_count_text or "-",
            "length": item.length_text or "-",
            "bpm": item.bpm_text or "-",
            "status": item.status_text or "-",
            "artist": item.artist_unicode or item.artist or "-",
            "name": item.name,
            "md5": item.md5 or "-",
        }

    def _on_beatmap_selected(self, _event=None) -> None:
        if not self.selected_collection:
            return
        selected = self.beatmap_tree.selection()
        if not selected:
            return
        index = int(selected[0].split("-")[-1])
        items = self.displayed_items
        if index < len(items):
            self.selected_item = items[index]
            self._load_preview_for_item(self.selected_item)

    def _toggle_beatmap_sort(self, column: str) -> None:
        if self.suppress_next_heading_sort:
            self.suppress_next_heading_sort = False
            return
        if self.sort_column == column:
            if not self.sort_descending:
                self.sort_descending = True
            else:
                self.sort_column = None
                self.sort_descending = False
        else:
            self.sort_column = column
            self.sort_descending = False
        self._refresh_beatmap_headings()
        self._refresh_beatmap_rows()

    def _refresh_beatmap_headings(self) -> None:
        for key, header, _, _, _ in COLUMN_DEFINITIONS:
            text = header
            if key == self.sort_column:
                text = f"{header} {'(DESC)' if self.sort_descending else '(ASC)'}"
            self.beatmap_tree.heading(key, text=text, command=lambda value=key: self._toggle_beatmap_sort(value))

    def _sorted_beatmap_items(self, items: list[BeatmapEntry]) -> list[BeatmapEntry]:
        if not self.sort_column:
            return list(reversed(items))

        valued_items: list[tuple[object, BeatmapEntry]] = []
        empty_items: list[BeatmapEntry] = []
        for item in items:
            sort_value = self._sort_value_for_item(item, self.sort_column)
            if sort_value is None:
                empty_items.append(item)
                continue
            valued_items.append((sort_value, item))

        valued_items.sort(key=lambda pair: pair[0], reverse=self.sort_descending)
        return [item for _, item in valued_items] + empty_items

    def _sort_value_for_item(self, item: BeatmapEntry, column: str) -> object | None:
        numeric_fields = {
            "star_rating": item.star_rating,
            "bid": item.beatmap_id,
            "sid": item.beatmap_set_id,
            "cs": item.circle_size,
            "od": item.overall_difficulty,
            "ar": item.approach_rate,
            "hp": item.drain_rate,
            "note_count": item.total_object_count,
            "length": item.length_ms,
            "bpm": item.bpm,
            "status": item.status_int,
        }
        if column in numeric_fields:
            value = numeric_fields[column]
            return None if value is None else float(value)

        text_fields = {
            "name_original": item.name_original,
            "artist": item.artist_unicode or item.artist,
            "difficulty_name": item.difficulty_name,
            "mapper": item.mapper,
            "mode": item.mode,
            "name": item.name,
            "md5": item.md5,
        }
        value = text_fields.get(column)
        if value is None:
            return None
        normalized = value.strip().casefold()
        return normalized or None

    def _on_beatmap_double_clicked(self, event=None) -> None:
        if event is not None:
            region = self.beatmap_tree.identify("region", event.x, event.y)
            if region != "cell":
                return
            row_id = self.beatmap_tree.identify_row(event.y)
            if not row_id:
                return
            index = int(row_id.split("-")[-1])
            if index < len(self.displayed_items):
                self.selected_item = self.displayed_items[index]
        if self.selected_item is not None:
            self._open_detail_popup(self.selected_item)

    def _center_beatmap_row(self, item_id: str, item_index: int, total_items: int) -> None:
        self.beatmap_tree.see(item_id)
        self.root.update_idletasks()
        bbox = self.beatmap_tree.bbox(item_id)
        if not bbox or total_items <= 1:
            return

        row_height = max(bbox[3], 1)
        visible_rows = max(self.beatmap_tree.winfo_height() // row_height, 1)
        max_first_index = max(total_items - visible_rows, 0)
        first_index = min(max(item_index - visible_rows // 2, 0), max_first_index)
        if max_first_index <= 0:
            self.beatmap_tree.yview_moveto(0)
            return
        self.beatmap_tree.yview_moveto(first_index / total_items)
        self.beatmap_tree.see(item_id)

    def _on_beatmap_tree_button_press(self, event) -> None:
        if self.beatmap_tree.identify("region", event.x, event.y) != "heading":
            self.dragged_heading_column = None
            self.dragged_heading_active = False
            return
        self.dragged_heading_column = self._display_column_key_from_x(event.x)
        self.dragged_heading_active = False
        self.drag_start_x = event.x

    def _on_beatmap_tree_drag(self, event) -> None:
        if self.dragged_heading_column is None:
            return
        if abs(event.x - self.drag_start_x) >= 8:
            self.dragged_heading_active = True

    def _on_beatmap_tree_button_release(self, event) -> None:
        if self.dragged_heading_column is None:
            return
        source_column = self.dragged_heading_column
        target_column = self._display_column_key_from_x(event.x)
        was_dragging = self.dragged_heading_active
        self.dragged_heading_column = None
        self.dragged_heading_active = False
        if not was_dragging or not target_column or target_column == source_column:
            return
        self._reorder_visible_columns(source_column, target_column)
        self.suppress_next_heading_sort = True

    def _display_column_key_from_x(self, x: int) -> str | None:
        column_id = self.beatmap_tree.identify_column(x)
        if not column_id.startswith("#"):
            return None
        try:
            column_index = int(column_id[1:]) - 1
        except ValueError:
            return None
        visible_keys = self._visible_column_keys()
        if 0 <= column_index < len(visible_keys):
            return visible_keys[column_index]
        return None

    def _reorder_visible_columns(self, source_column: str, target_column: str) -> None:
        visible_keys = self._visible_column_keys()
        if source_column not in visible_keys or target_column not in visible_keys:
            return

        reordered_visible = list(visible_keys)
        source_index = reordered_visible.index(source_column)
        target_index = reordered_visible.index(target_column)
        reordered_visible.pop(source_index)
        if source_index < target_index:
            target_index -= 1
        reordered_visible.insert(target_index, source_column)

        hidden_keys = [key for key in self.column_order if key not in visible_keys]
        self.column_order = reordered_visible + hidden_keys
        self._save_column_visibility()
        self._apply_column_visibility()

    def _clear_preview(self, text: str = "选择谱面后在这里显示背景图") -> None:
        self.preview_request_id += 1
        self.preview_photo = None
        self.preview_cover_path = None
        self.preview_label.configure(image="", text=text)

    def _on_preview_configure(self, _event=None) -> None:
        if self.preview_resize_job is not None:
            self.root.after_cancel(self.preview_resize_job)
        self.preview_resize_job = self.root.after(80, self._refresh_preview_layout)

    def _refresh_preview_layout(self) -> None:
        self.preview_resize_job = None
        if self.preview_cover_path and self.preview_cover_path.exists():
            self._render_preview_cover(self.preview_cover_path)

    def _load_preview_for_item(self, item) -> None:
        request_id = self.preview_request_id + 1
        self.preview_request_id = request_id

        if item is None:
            self._clear_preview()
            return
        if item.missing:
            self.preview_photo = None
            self.preview_label.configure(image="", text="该条目缺少本地谱面信息")
            return

        self.preview_label.configure(image="", text="正在加载背景图...")

        def worker() -> None:
            with self.cover_load_limiter:
                cover_path = self.cover_cache.get_cover_path(item.beatmap_set_id)
            self.root.after(0, lambda: self._apply_preview_cover(request_id, cover_path))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_preview_cover(self, request_id: int, cover_path: Path | None) -> None:
        if request_id != self.preview_request_id:
            return
        if cover_path is None or not cover_path.exists():
            self.preview_photo = None
            self.preview_cover_path = None
            self.preview_label.configure(image="", text="暂无可用图片")
            return

        self.preview_cover_path = cover_path
        self._render_preview_cover(cover_path)

    def _render_preview_cover(self, cover_path: Path) -> None:
        width = max(self.preview_label.winfo_width() - 12, 120)
        height = max(self.preview_label.winfo_height() - 12, 90)
        image = Image.open(cover_path).convert("RGB")
        image = ImageOps.contain(image, (width, height), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(image)
        self.preview_label.configure(image=self.preview_photo, text="")

    def _open_detail_popup(self, item) -> None:
        if self.detail_popup and self.detail_popup.winfo_exists():
            self.detail_popup.destroy()

        popup = tk.Toplevel(self.root)
        popup.title("谱面详情")
        popup.transient(self.root)
        popup.configure(padx=12, pady=12, bg="#f8fafc")
        popup.minsize(860, 460)
        popup.protocol("WM_DELETE_WINDOW", popup.destroy)
        self.detail_popup = popup
        self._apply_window_icon(popup)

        shell = ttk.Frame(popup)
        shell.pack(fill=tk.BOTH, expand=True)

        cover_frame = ttk.LabelFrame(shell, text="背景图", padding=6)
        cover_frame.pack(fill=tk.X)
        cover_label = ttk.Label(cover_frame, text="正在加载图片...", anchor=tk.CENTER, justify=tk.CENTER)
        cover_label.pack(fill=tk.BOTH, expand=True)

        info_frame = ttk.LabelFrame(shell, text="详细信息", padding=10)
        info_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        info_frame.columnconfigure(0, weight=1)

        ttk.Label(
            info_frame,
            text=item.name_original or "-",
            style="PopupTitle.TLabel",
            wraplength=760,
            justify=tk.LEFT,
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        detail_grid = ttk.Frame(info_frame)
        detail_grid.grid(row=1, column=0, sticky="nsew")
        for column in range(4):
            detail_grid.columnconfigure(column, weight=1, uniform="popup")

        fields = [
            ("名称", item.name or "-"),
            ("艺术家（原语言）", item.artist_unicode or item.artist or "-"),
            ("谱师", item.mapper or "-"),
            ("难度名", item.difficulty_name or "-"),
            ("模式", item.mode),
            ("状态", item.status_text or "-"),
            ("难度", item.star_rating_text or "-"),
            ("长度", item.length_text or "-"),
            ("BPM", item.bpm_text or "-"),
            ("Note数", item.note_count_text or "-"),
            ("BID", item.bid_text or "-"),
            ("SID", item.sid_text or "-"),
            ("CS", item.cs_text or "-"),
            ("AR", item.ar_text or "-"),
            ("OD", item.od_text or "-"),
            ("HP", item.hp_text or "-"),
            ("MD5", item.md5 or "-"),
        ]
        for index, (label, value) in enumerate(fields):
            row = index // 4
            column = index % 4
            columnspan = 4 if label == "MD5" else 1
            wraplength = 720 if label == "MD5" else 150
            field = ttk.Frame(detail_grid)
            field.grid(row=row, column=column, columnspan=columnspan, sticky="nsew", padx=(0, 10), pady=(0, 8))
            ttk.Label(field, text=label, style="PopupField.TLabel").pack(anchor=tk.W)
            ttk.Label(
                field,
                text=value,
                style="PopupValue.TLabel",
                wraplength=wraplength,
                justify=tk.LEFT,
            ).pack(anchor=tk.W, pady=(1, 0))

        popup.update_idletasks()
        popup_width = popup.winfo_width()
        popup_height = popup.winfo_height()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - popup_width) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - popup_height) // 2 - 150
        popup.geometry(f"+{max(x, 0)}+{max(y, 0)}")

        if item.missing:
            cover_label.configure(text="该条目缺少本地谱面信息")
            return

        threading.Thread(
            target=self._load_popup_cover,
            args=(item.beatmap_set_id, popup, cover_label),
            daemon=True,
        ).start()

    def _load_popup_cover(self, beatmap_set_id: int | None, popup: tk.Toplevel, cover_label: ttk.Label) -> None:
        with self.cover_load_limiter:
            cover_path = self.cover_cache.get_cover_path(beatmap_set_id)
        self.root.after(0, lambda: self._apply_popup_cover(popup, cover_label, cover_path))

    def _apply_popup_cover(self, popup: tk.Toplevel, cover_label: ttk.Label, cover_path: Path | None) -> None:
        if not popup.winfo_exists():
            return
        if cover_path is None or not cover_path.exists():
            cover_label.configure(text="暂无可用图片")
            return

        image = Image.open(cover_path).convert("RGB")
        image = ImageOps.contain(image, (760, 240), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image)
        cover_label.configure(image=photo, text="")
        cover_label.image = photo


def launch() -> None:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("osulazer-collection-view.app")
    except Exception:  # noqa: BLE001
        pass
    root = tk.Tk()
    CollectionViewApp(root)
    root.mainloop()
