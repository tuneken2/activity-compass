from __future__ import annotations

import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from .db import Database


COLORS = {
    "bg": "#F5F4EF",
    "panel": "#FFFFFF",
    "sidebar": "#17211D",
    "sidebar_text": "#DCE7E1",
    "accent": "#D4673D",
    "accent_dark": "#A84628",
    "text": "#1E2925",
    "muted": "#6E7773",
    "line": "#DEDCD3",
    "soft": "#ECE9DF",
    "row_alt": "#FAFAF7",
    "selected": "#F3E4DC",
    "selected_line": "#D4673D",
}

LABELS = {
    "today": "今日",
    "next": "次にやる",
    "waiting": "待ち",
    "someday": "いつか",
    "projects": "プロジェクト",
    "review": "確認待ち",
    "history": "更新履歴",
    "all": "すべて",
}

TYPE_LABELS = {
    "task": "タスク",
    "schedule": "予定",
    "idea": "アイデア",
    "waiting": "待ち",
    "decision": "決定",
    "project": "プロジェクト",
}

STATUS_LABELS = {
    "inbox": "未整理",
    "today": "今日",
    "next": "次に",
    "in_progress": "進行中",
    "waiting": "待ち",
    "someday": "いつか",
    "done": "完了",
    "cancelled": "取消",
}

TYPE_COLORS = {
    "task": ("#E8F0EC", "#315E4F"),
    "schedule": ("#E7EEF5", "#355B78"),
    "idea": ("#F4EEDB", "#795F19"),
    "waiting": ("#EFEAE5", "#6C5747"),
    "decision": ("#EEE7F2", "#684B76"),
    "project": ("#F5E6DF", "#8A482F"),
}

DEFAULT_VIEW = "projects"


def format_priority(priority: Any) -> str:
    try:
        value = int(priority or 0)
    except (TypeError, ValueError):
        value = 0
    return {3: "高", 2: "中", 1: "低"}.get(value, "—")


def format_list_date(value: str | None, kind: str) -> tuple[str, str]:
    """Return a short, scan-friendly date and its small contextual label."""
    if not value:
        return "無期限", "締切なし"
    try:
        item_date = datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            item_date = datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return value[:10], kind

    today = date.today()
    if kind == "期限" and item_date < today:
        return "期限超過", item_date.strftime("%m/%d")
    if item_date == today:
        return "今日", kind
    if item_date == today + timedelta(days=1):
        return "明日", kind
    if item_date.year == today.year:
        return f"{item_date.month}/{item_date.day}", kind
    return f"{item_date.year}/{item_date.month}/{item_date.day}", kind


class ActivityCompassApp(tk.Tk):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.current_view = DEFAULT_VIEW
        self.expanded_project_ids: set[str] = set()
        self.search_query = ""
        self.rows: dict[str, dict[str, Any]] = {}
        self.row_widgets: dict[str, dict[str, Any]] = {}
        self.selected_id: str | None = None
        self.title("Activity Compass")
        icon_path = Path(__file__).resolve().parents[2] / "assets" / "activity-compass.png"
        try:
            self._app_icon = tk.PhotoImage(file=icon_path)
            self.iconphoto(True, self._app_icon)
        except tk.TclError:
            self._app_icon = None
        self.geometry("1160x720")
        self.minsize(940, 600)
        self.configure(bg=COLORS["bg"])
        self._configure_styles()
        self._build()
        self.refresh()
        self.after(3000, self._poll)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Vertical.TScrollbar", gripcount=0, borderwidth=0)

    def _build(self) -> None:
        sidebar = tk.Frame(self, bg=COLORS["sidebar"], width=190)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(
            sidebar,
            text="ACTIVITY\nCOMPASS",
            justify="left",
            bg=COLORS["sidebar"],
            fg="white",
            font=("Segoe UI Semibold", 17),
        ).pack(anchor="w", padx=24, pady=(28, 36))

        self.nav_buttons: dict[str, tk.Button] = {}
        for key in ("projects", "today", "next", "waiting", "someday", "review", "history", "all"):
            button = tk.Button(
                sidebar,
                text=LABELS[key],
                anchor="w",
                padx=22,
                pady=11,
                relief="flat",
                borderwidth=0,
                bg=COLORS["sidebar"],
                fg=COLORS["sidebar_text"],
                activebackground="#2B3833",
                activeforeground="white",
                font=("Segoe UI", 10),
                command=lambda value=key: self.change_view(value),
            )
            button.pack(fill="x")
            self.nav_buttons[key] = button

        tk.Button(
            sidebar,
            text="データを書き出す",
            anchor="w",
            padx=22,
            pady=11,
            relief="flat",
            borderwidth=0,
            bg=COLORS["sidebar"],
            fg="#9FB0A8",
            activebackground="#2B3833",
            activeforeground="white",
            font=("Segoe UI", 9),
            command=self.export_data,
        ).pack(fill="x", pady=(18, 0))

        tk.Label(
            sidebar,
            text="会話で決まったことを\n頭の外へ。",
            justify="left",
            bg=COLORS["sidebar"],
            fg="#84948C",
            font=("Segoe UI", 9),
        ).pack(side="bottom", anchor="w", padx=24, pady=24)

        main = tk.Frame(self, bg=COLORS["bg"])
        main.pack(side="left", fill="both", expand=True)

        header = tk.Frame(main, bg=COLORS["bg"])
        header.pack(fill="x", padx=28, pady=(24, 14))
        self.heading = tk.Label(
            header,
            text="プロジェクト",
            bg=COLORS["bg"],
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 23),
        )
        self.heading.pack(side="left")
        self.count_label = tk.Label(
            header,
            text="",
            bg=COLORS["bg"],
            fg=COLORS["muted"],
            font=("Segoe UI", 10),
        )
        self.count_label.pack(side="left", padx=12, pady=(8, 0))
        self.search_entry = tk.Entry(
            header,
            width=26,
            relief="flat",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            font=("Segoe UI", 10),
        )
        self.search_entry.pack(side="right", ipady=7, padx=(8, 0))
        self.search_entry.insert(0, "検索")
        self.search_entry.bind("<FocusIn>", self._clear_search_placeholder)
        self.search_entry.bind("<Return>", lambda _: self.perform_search())

        add_frame = tk.Frame(main, bg=COLORS["panel"], highlightbackground=COLORS["line"], highlightthickness=1)
        add_frame.pack(fill="x", padx=28, pady=(0, 14))
        self.quick_entry = tk.Entry(
            add_frame,
            relief="flat",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            font=("Segoe UI", 11),
        )
        self.quick_entry.pack(side="left", fill="x", expand=True, padx=14, pady=12)
        self.quick_entry.insert(0, "新しいタスクを追加")
        self.quick_entry.bind("<FocusIn>", self._clear_placeholder)
        self.quick_entry.bind("<Return>", lambda _: self.quick_add())
        tk.Button(
            add_frame,
            text="追加",
            command=self.quick_add,
            bg=COLORS["accent"],
            fg="white",
            activebackground=COLORS["accent_dark"],
            relief="flat",
            padx=22,
            pady=9,
            font=("Segoe UI Semibold", 9),
        ).pack(side="right", padx=6, pady=6)

        content = tk.PanedWindow(main, orient="horizontal", sashwidth=6, bg=COLORS["bg"], bd=0)
        content.pack(fill="both", expand=True, padx=28, pady=(0, 24))

        list_panel = tk.Frame(
            content,
            bg=COLORS["panel"],
            highlightbackground=COLORS["line"],
            highlightthickness=1,
        )
        detail_panel = tk.Frame(content, bg=COLORS["panel"], width=300)
        content.add(list_panel, stretch="always", minsize=500)
        content.add(detail_panel, stretch="never", minsize=260)

        list_header = tk.Frame(list_panel, bg=COLORS["soft"], height=38)
        list_header.pack(fill="x")
        list_header.pack_propagate(False)
        tk.Label(
            list_header,
            text="項目",
            bg=COLORS["soft"],
            fg=COLORS["muted"],
            font=("Segoe UI Semibold", 9),
        ).pack(side="left", padx=16)
        tk.Label(
            list_header,
            text="期限 / 予定",
            bg=COLORS["soft"],
            fg=COLORS["muted"],
            font=("Segoe UI Semibold", 9),
        ).pack(side="right", padx=(8, 20))
        tk.Label(
            list_header,
            text="優先度",
            bg=COLORS["soft"],
            fg=COLORS["muted"],
            font=("Segoe UI Semibold", 9),
        ).pack(side="right", padx=(8, 18))

        list_body = tk.Frame(list_panel, bg=COLORS["panel"])
        list_body.pack(fill="both", expand=True)
        self.list_canvas = tk.Canvas(
            list_body,
            bg=COLORS["panel"],
            bd=0,
            highlightthickness=0,
        )
        list_scrollbar = ttk.Scrollbar(
            list_body, orient="vertical", command=self.list_canvas.yview
        )
        self.list_canvas.configure(yscrollcommand=list_scrollbar.set)
        list_scrollbar.pack(side="right", fill="y")
        self.list_canvas.pack(side="left", fill="both", expand=True)
        self.list_rows = tk.Frame(self.list_canvas, bg=COLORS["panel"])
        self.list_window = self.list_canvas.create_window(
            (0, 0), window=self.list_rows, anchor="nw"
        )
        self.list_rows.bind(
            "<Configure>",
            lambda _: self.list_canvas.configure(
                scrollregion=self.list_canvas.bbox("all")
            ),
        )
        self.list_canvas.bind(
            "<Configure>",
            lambda event: self.list_canvas.itemconfigure(
                self.list_window, width=event.width
            ),
        )
        self.list_canvas.bind("<MouseWheel>", self._scroll_list)

        tk.Label(
            detail_panel,
            text="詳細",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w", padx=20, pady=(20, 8))
        self.detail_title = tk.Label(
            detail_panel,
            text="項目を選択してください",
            wraplength=260,
            justify="left",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 15),
        )
        self.detail_title.pack(anchor="w", padx=20)
        self.detail_meta = tk.Label(
            detail_panel,
            text="",
            wraplength=260,
            justify="left",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
        )
        self.detail_meta.pack(anchor="w", padx=20, pady=(8, 12))
        self.detail_text = tk.Text(
            detail_panel,
            height=12,
            wrap="word",
            relief="flat",
            bg="#FAF9F5",
            fg=COLORS["text"],
            padx=12,
            pady=12,
            font=("Segoe UI", 9),
        )
        self.detail_text.pack(fill="both", expand=True, padx=20, pady=(0, 14))
        self.actions = tk.Frame(detail_panel, bg=COLORS["panel"])
        self.actions.pack(fill="x", padx=20, pady=(0, 20))

    def _clear_placeholder(self, _: tk.Event) -> None:
        if self.quick_entry.get() == "新しいタスクを追加":
            self.quick_entry.delete(0, "end")

    def _clear_search_placeholder(self, _: tk.Event) -> None:
        if self.search_entry.get() == "検索":
            self.search_entry.delete(0, "end")

    def quick_add(self) -> None:
        title = self.quick_entry.get().strip()
        if not title or title == "新しいタスクを追加":
            return
        self.db.create_item({"entity_type": "task", "title": title, "status": "inbox"})
        self.quick_entry.delete(0, "end")
        self.refresh()

    def change_view(self, view: str) -> None:
        self.current_view = view
        self.search_query = ""
        self.search_entry.delete(0, "end")
        self.search_entry.insert(0, "検索")
        self.heading.configure(text=LABELS[view])
        self.refresh()

    def perform_search(self) -> None:
        value = self.search_entry.get().strip()
        self.search_query = "" if value == "検索" else value
        self.heading.configure(text=f"検索: {self.search_query}" if self.search_query else LABELS[self.current_view])
        self.refresh()

    def refresh(self) -> None:
        if self.search_query:
            data = self.db.search_items(self.search_query)
        elif self.current_view == "history":
            data = self.db.list_history()
        else:
            data = self.db.list_items(self.current_view)
        project_tasks: dict[str, list[dict[str, Any]]] = {}
        if self.current_view == "projects" and not self.search_query:
            for task in self.db.list_items("project_tasks"):
                project_tasks.setdefault(task["project_id"], []).append(task)
        counts = self.db.counts()
        self.count_label.configure(text=f"{len(data)}件")
        for key, button in self.nav_buttons.items():
            suffix = f"   {counts.get(key, '')}" if key in counts else ""
            button.configure(
                text=f"{LABELS[key]}{suffix}",
                bg="#2B3833" if key == self.current_view else COLORS["sidebar"],
                fg="white" if key == self.current_view else COLORS["sidebar_text"],
            )
        scroll_position = self.list_canvas.yview()[0]
        selected_id = self.selected_id
        for child in self.list_rows.winfo_children():
            child.destroy()
        self.rows.clear()
        self.row_widgets.clear()
        display_data: list[tuple[dict[str, Any], bool]] = []
        if self.current_view == "projects" and not self.search_query:
            for project in data:
                display_data.append((project, False))
                if project["id"] in self.expanded_project_ids:
                    display_data.extend(
                        (task, True) for task in project_tasks.get(project["id"], [])
                    )
        else:
            display_data = [(row, False) for row in data]

        for index, (row, is_project_child) in enumerate(display_data):
            is_review = self.current_view == "review" and not self.search_query
            is_history = self.current_view == "history" and not self.search_query
            row_id = row["id"]
            if is_review:
                title = row["title"]
                kind = row["action"]
                status = "確認待ち"
                date_value = row["created_at"]
                date_kind = "受付"
            elif is_history:
                title = row.get("title") or "削除済み項目"
                kind = row["action"]
                status = "履歴"
                date_value = row["created_at"]
                date_kind = "更新"
            else:
                title = f"    ↳ {row['title']}" if is_project_child else row["title"]
                kind = TYPE_LABELS.get(row["entity_type"], row["entity_type"])
                if (
                    self.current_view == "projects"
                    and not self.search_query
                    and row["entity_type"] == "project"
                ):
                    child_count = len(project_tasks.get(row_id, []))
                    marker = "▼" if row_id in self.expanded_project_ids else "▶"
                    title = f"{marker}  {title}"
                    status = (
                        f"子タスク {child_count}件 · "
                        f"{'クリックで閉じる' if row_id in self.expanded_project_ids else 'クリックで展開'}"
                    )
                else:
                    status = STATUS_LABELS.get(row["status"], row["status"])
                date_value = row.get("due_at") or row.get("scheduled_at") or ""
                date_kind = "期限" if row.get("due_at") else "予定"
            self.rows[row_id] = row
            self._build_list_row(
                row_id=row_id,
                row=row,
                title=title,
                kind=kind,
                status=status,
                date_value=date_value,
                date_kind=date_kind,
                alternate=index % 2 == 1,
                on_click=(
                    (lambda value=row_id: self._toggle_project(value))
                    if self.current_view == "projects"
                    and not self.search_query
                    and row["entity_type"] == "project"
                    else None
                ),
            )
        if selected_id in self.rows:
            self._select_row(selected_id, show_details=False)
        else:
            self.selected_id = None
            self._clear_detail()
        self.after_idle(lambda: self.list_canvas.yview_moveto(scroll_position))

    def _build_list_row(
        self,
        *,
        row_id: str,
        row: dict[str, Any],
        title: str,
        kind: str,
        status: str,
        date_value: str | None,
        date_kind: str,
        alternate: bool,
        on_click: Callable[[], None] | None = None,
    ) -> None:
        base_bg = COLORS["row_alt"] if alternate else COLORS["panel"]
        entity_type = row.get("entity_type", "task")
        badge_bg, badge_fg = TYPE_COLORS.get(
            entity_type, (COLORS["soft"], COLORS["muted"])
        )
        category = (
            row.get("category")
            if entity_type == "project"
            else row.get("project_category")
        )
        category_color = (
            row.get("category_color")
            if entity_type == "project"
            else row.get("project_category_color")
        )
        project_color = (
            row.get("project_color")
            if entity_type == "project"
            else row.get("project_image_color")
        )
        accent_color = badge_fg if not (
            self.current_view in {"review", "history"} and not self.search_query
        ) else COLORS["muted"]
        if project_color:
            accent_color = project_color

        item = tk.Frame(
            self.list_rows,
            bg=base_bg,
            height=66,
            highlightbackground=COLORS["line"],
            highlightthickness=0,
        )
        item.pack(fill="x")
        item.pack_propagate(False)
        accent = tk.Frame(item, bg=accent_color, width=6)
        accent.pack(side="left", fill="y")
        accent.pack_propagate(False)

        due_text, due_context = format_list_date(date_value, date_kind)
        due = tk.Frame(item, bg=base_bg, width=104)
        due.pack(side="right", fill="y")
        due.pack_propagate(False)
        due_title = tk.Label(
            due,
            text=due_text,
            bg=base_bg,
            fg=COLORS["accent_dark"] if due_text == "期限超過" else COLORS["text"],
            font=("Segoe UI Semibold", 9),
            anchor="e",
        )
        due_title.pack(fill="x", padx=(4, 16), pady=(14, 0))
        due_label = tk.Label(
            due,
            text=due_context,
            bg=base_bg,
            fg=COLORS["muted"],
            font=("Segoe UI", 8),
            anchor="e",
        )
        due_label.pack(fill="x", padx=(4, 16))

        priority_text = format_priority(row.get("priority"))
        priority_column = tk.Label(
            item,
            text=priority_text,
            bg=base_bg,
            fg=COLORS["accent"],
            font=("Segoe UI Semibold", 8),
            width=7,
        )
        priority_column.pack(side="right", fill="y")

        body = tk.Frame(item, bg=base_bg)
        body.pack(side="left", fill="both", expand=True, padx=(14, 6))
        title_label = tk.Label(
            body,
            text=title,
            bg=base_bg,
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 10),
            anchor="w",
        )
        title_label.pack(fill="x", pady=(9, 3))
        meta = tk.Frame(body, bg=base_bg)
        meta.pack(fill="x")
        kind_label = tk.Label(
            meta,
            text=f"  {kind}  ",
            bg=badge_bg,
            fg=badge_fg,
            font=("Segoe UI Semibold", 8),
        )
        kind_label.pack(side="left")
        category_label: tk.Label | None = None
        if category:
            category_label = tk.Label(
                meta,
                text=f"  {category}  ",
                bg=category_color or COLORS["muted"],
                fg="white",
                font=("Segoe UI Semibold", 8),
            )
            category_label.pack(side="left", padx=(6, 0))
        status_label = tk.Label(
            meta,
            text=status,
            bg=base_bg,
            fg=COLORS["muted"],
            font=("Segoe UI", 8),
        )
        status_label.pack(side="left", padx=(8, 0))
        separator = tk.Frame(self.list_rows, bg=COLORS["line"], height=1)
        separator.pack(fill="x")

        surfaces: list[tk.Widget] = [
            item,
            due,
            due_title,
            due_label,
            body,
            title_label,
            meta,
            status_label,
            priority_column,
        ]
        clickable = surfaces + [accent, kind_label]
        if category_label:
            clickable.append(category_label)
        for widget in clickable:
            if on_click:
                widget.bind("<Button-1>", lambda _, action=on_click: action())
            else:
                widget.bind("<Button-1>", lambda _, value=row_id: self._select_row(value))
            widget.bind("<MouseWheel>", self._scroll_list)

        self.row_widgets[row_id] = {
            "item": item,
            "accent": accent,
            "accent_color": accent_color,
            "base_bg": base_bg,
            "surfaces": surfaces,
        }

    def _toggle_project(self, project_id: str) -> None:
        if project_id in self.expanded_project_ids:
            self.expanded_project_ids.remove(project_id)
        else:
            self.expanded_project_ids.add(project_id)
        self.selected_id = project_id
        self.refresh()
        if project_id in self.rows:
            self._select_row(project_id)

    def _select_row(self, row_id: str, show_details: bool = True) -> None:
        if self.selected_id in self.row_widgets:
            previous = self.row_widgets[self.selected_id]
            for widget in previous["surfaces"]:
                widget.configure(bg=previous["base_bg"])
            previous["accent"].configure(bg=previous["accent_color"])

        self.selected_id = row_id
        current = self.row_widgets.get(row_id)
        if current:
            for widget in current["surfaces"]:
                widget.configure(bg=COLORS["selected"])
        if show_details:
            self.show_detail()

    def _clear_detail(self) -> None:
        self.detail_title.configure(text="項目を選択してください")
        self.detail_meta.configure(text="")
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.configure(state="disabled")
        for child in self.actions.winfo_children():
            child.destroy()

    def _scroll_list(self, event: tk.Event) -> str:
        self.list_canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def show_detail(self, _: tk.Event | None = None) -> None:
        if not self.selected_id or self.selected_id not in self.rows:
            return
        row = self.rows[self.selected_id]
        self.detail_title.configure(text=row["title"])
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        for child in self.actions.winfo_children():
            child.destroy()
        if self.current_view == "review" and not self.search_query:
            self.detail_meta.configure(text=f"{row['action']} · {row['created_at'][:16]}")
            self.detail_text.insert("1.0", row["reason"])
            self._action_button("承認", lambda: self.resolve_review(row["id"], True), COLORS["accent"])
            self._action_button("却下", lambda: self.resolve_review(row["id"], False), "#77736B")
            self.detail_text.configure(state="disabled")
        elif self.current_view == "history" and not self.search_query:
            self.detail_meta.configure(text=f"{row['action']} · {row['created_at'][:16]}")
            self.detail_text.insert("1.0", row.get("payload_json") or "")
            self.detail_text.configure(state="disabled")
        else:
            self.detail_meta.configure(
                text=f"{TYPE_LABELS.get(row['entity_type'], row['entity_type'])} · {row['status']}"
            )
            self.detail_text.insert("1.0", row.get("details") or "詳細はまだありません。")
            self._action_button("編集", lambda: self.open_editor(row), "#3C7160")
            self._action_button("保存", lambda: self.save_details(row["id"]), "#3C7160")
            self._action_button("完了", lambda: self.set_status(row["id"], "done"), COLORS["accent"])
            self._action_button("進行中", lambda: self.set_status(row["id"], "in_progress"), "#3C7160")
            self._action_button("次に", lambda: self.set_status(row["id"], "next"), "#3C7160")
            self._action_button("待ち", lambda: self.set_status(row["id"], "waiting"), "#77736B")
            self._action_button("いつか", lambda: self.set_status(row["id"], "someday"), "#77736B")

    def _action_button(self, text: str, command: Any, color: str) -> None:
        tk.Button(
            self.actions,
            text=text,
            command=command,
            bg=color,
            fg="white",
            activebackground=color,
            relief="flat",
            padx=10,
            pady=7,
            font=("Segoe UI Semibold", 8),
        ).pack(side="left", padx=(0, 5))

    def set_status(self, item_id: str, status: str) -> None:
        self.db.update_status(item_id, status)
        self.refresh()

    def save_details(self, item_id: str) -> None:
        details = self.detail_text.get("1.0", "end").strip()
        if details == "詳細はまだありません。":
            details = ""
        self.db.update_item(item_id, {"details": details})
        self.refresh()

    def open_editor(self, item: dict[str, Any]) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("項目を編集")
        dialog.geometry("480x660")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg=COLORS["bg"])

        fields = tk.Frame(dialog, bg=COLORS["bg"])
        fields.pack(fill="both", expand=True, padx=24, pady=20)

        def labeled_entry(label: str, value: str = "") -> tk.Entry:
            tk.Label(
                fields, text=label, bg=COLORS["bg"], fg=COLORS["muted"],
                font=("Segoe UI Semibold", 9),
            ).pack(anchor="w", pady=(8, 3))
            entry = tk.Entry(fields, relief="flat", font=("Segoe UI", 10))
            entry.pack(fill="x", ipady=6)
            entry.insert(0, value)
            return entry

        title = labeled_entry("タイトル", item.get("title", ""))
        tk.Label(
            fields, text="種類 / 状態", bg=COLORS["bg"], fg=COLORS["muted"],
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w", pady=(10, 3))
        pair = tk.Frame(fields, bg=COLORS["bg"])
        pair.pack(fill="x")
        entity_type = ttk.Combobox(
            pair,
            values=("task", "schedule", "idea", "waiting", "decision", "project"),
            state="readonly",
        )
        entity_type.set(item.get("entity_type", "task"))
        entity_type.pack(side="left", fill="x", expand=True, padx=(0, 5))
        status = ttk.Combobox(
            pair,
            values=(
                "inbox",
                "today",
                "next",
                "in_progress",
                "waiting",
                "someday",
                "done",
                "cancelled",
            ),
            state="readonly",
        )
        status.set(item.get("status", "inbox"))
        status.pack(side="left", fill="x", expand=True, padx=(5, 0))
        category = labeled_entry(
            "カテゴリー（プロジェクトのみ・色は自動設定）",
            item.get("category") or "",
        )
        due_at = labeled_entry("期限（空欄なら無期限）", item.get("due_at") or "")
        scheduled_at = labeled_entry("予定日時（例: 2026-08-03 10:00）", item.get("scheduled_at") or "")
        effort = labeled_entry("実装難易度 / 工数（1〜5）", str(item.get("effort") or 3))
        priority = labeled_entry(
            "優先度（数字で入力: 3=高 / 2=中 / 1=低）",
            str(item.get("priority") or 2),
        )
        project_rank = labeled_entry(
            "同一優先度内の序列（プロジェクトのみ・1が先頭）",
            str(item.get("project_rank") or ""),
        )
        tk.Label(
            fields,
            text=f"現在の表示: {format_priority(item.get('priority'))}  {item.get('priority_reason', '')}",
            bg=COLORS["bg"],
            fg=COLORS["muted"],
            font=("Segoe UI", 8),
            wraplength=420,
            justify="left",
        ).pack(anchor="w", pady=(5, 0))
        tk.Label(
            fields, text="詳細", bg=COLORS["bg"], fg=COLORS["muted"],
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w", pady=(10, 3))
        details = tk.Text(fields, height=6, relief="flat", font=("Segoe UI", 10))
        details.pack(fill="both", expand=True)
        details.insert("1.0", item.get("details") or "")

        def save() -> None:
            try:
                self.db.update_item(
                    item["id"],
                    {
                        "title": title.get(),
                        "entity_type": entity_type.get(),
                        "status": status.get(),
                        "due_at": due_at.get().strip() or None,
                        "scheduled_at": scheduled_at.get().strip() or None,
                        "effort": max(1, min(5, int(effort.get() or 3))),
                        "priority": max(1, min(3, int(priority.get() or 2))),
                        "project_rank": (
                            int(project_rank.get())
                            if entity_type.get() == "project"
                            and project_rank.get().strip()
                            else None
                        ),
                        "category": category.get(),
                        "details": details.get("1.0", "end").strip(),
                    },
                )
                dialog.destroy()
                self.refresh()
            except Exception as exc:
                messagebox.showerror("Activity Compass", str(exc), parent=dialog)

        tk.Button(
            dialog,
            text="保存",
            command=save,
            bg=COLORS["accent"],
            fg="white",
            relief="flat",
            padx=24,
            pady=9,
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="e", padx=24, pady=(0, 20))

    def resolve_review(self, review_id: str, approve: bool) -> None:
        try:
            self.db.resolve_review(review_id, approve)
            self.refresh()
        except Exception as exc:
            messagebox.showerror("Activity Compass", str(exc))

    def export_data(self) -> None:
        default_name = f"activity-compass-{datetime.now():%Y-%m-%d}.json"
        path = filedialog.asksaveasfilename(
            title="Activity Compassのデータを書き出す",
            defaultextension=".json",
            initialfile=default_name,
            filetypes=[("JSON", "*.json")],
        )
        if path:
            self.db.export_json(path)
            messagebox.showinfo("Activity Compass", "データを書き出しました。")

    def show_due_notifications(self) -> None:
        for item in self.db.due_notifications():
            self.db.mark_notified(item["id"], item["trigger_key"])
            popup = tk.Toplevel(self)
            popup.title("Activity Compass")
            popup.configure(bg=COLORS["sidebar"])
            popup.attributes("-topmost", True)
            width, height = 340, 120
            x = self.winfo_screenwidth() - width - 24
            y = self.winfo_screenheight() - height - 72
            popup.geometry(f"{width}x{height}+{x}+{y}")
            tk.Label(
                popup,
                text="そろそろです",
                bg=COLORS["sidebar"],
                fg="#9FB0A8",
                font=("Segoe UI Semibold", 9),
            ).pack(anchor="w", padx=18, pady=(15, 4))
            tk.Label(
                popup,
                text=item["title"],
                wraplength=300,
                justify="left",
                bg=COLORS["sidebar"],
                fg="white",
                font=("Segoe UI Semibold", 12),
            ).pack(anchor="w", padx=18)
            popup.after(12000, popup.destroy)

    def _poll(self) -> None:
        self.refresh()
        self.show_due_notifications()
        self.after(3000, self._poll)
