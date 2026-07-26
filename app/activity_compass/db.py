from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
import zlib
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator


DESTRUCTIVE_ACTIONS = {"complete", "cancel", "defer"}
VALID_TYPES = {"task", "schedule", "idea", "waiting", "decision", "project"}
VALID_STATUSES = {"inbox", "today", "next", "waiting", "someday", "done", "cancelled"}
CORRUPTED_TEXT_PATTERN = re.compile(r"\?{3,}|\ufffd")
EFFORT_EASY_PATTERN = re.compile(r"短時間|軽微|簡単|すぐ|小規模|quick|easy", re.IGNORECASE)
EFFORT_HARD_PATTERN = re.compile(
    r"高難度|複雑|大規模|全面|設計|調査|研究|統合|移行|実装|パイプライン|"
    r"architecture|migration|complex",
    re.IGNORECASE,
)
PROJECT_RANK_PATTERN = re.compile(r"優先(?:順位|度)\s*[:：]?\s*(\d+)")
CATEGORY_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
CATEGORY_COLORS = (
    "#3C7160",
    "#527792",
    "#9B7B28",
    "#7E5D8D",
    "#B15939",
    "#477A7A",
    "#8A5F73",
    "#657547",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_db_path() -> Path:
    configured = os.environ.get("ACTIVITY_COMPASS_DB")
    if configured:
        return Path(configured).expanduser().resolve()
    base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    return base / "ActivityCompass" / "activity.db"


def normalize_title(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def validate_text_integrity(value: Any) -> None:
    """Reject text that was probably destroyed by a lossy encoding conversion."""
    if isinstance(value, str):
        if CORRUPTED_TEXT_PATTERN.search(value):
            raise ValueError(
                "text appears corrupted; send JSON as UTF-8 without a PowerShell native pipeline"
            )
        return
    if isinstance(value, dict):
        for nested in value.values():
            validate_text_integrity(nested)
        return
    if isinstance(value, (list, tuple)):
        for nested in value:
            validate_text_integrity(nested)


class Database:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS items (
                    id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    normalized_title TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'inbox',
                    due_at TEXT,
                    scheduled_at TEXT,
                    priority INTEGER NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
                CREATE INDEX IF NOT EXISTS idx_items_identity
                    ON items(entity_type, normalized_title);

                CREATE TABLE IF NOT EXISTS sync_batches (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT UNIQUE,
                    source TEXT NOT NULL,
                    source_summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS activity_events (
                    id TEXT PRIMARY KEY,
                    batch_id TEXT,
                    action TEXT NOT NULL,
                    item_id TEXT,
                    payload_json TEXT NOT NULL,
                    source_excerpt TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(batch_id) REFERENCES sync_batches(id),
                    FOREIGN KEY(item_id) REFERENCES items(id)
                );

                CREATE TABLE IF NOT EXISTS review_queue (
                    id TEXT PRIMARY KEY,
                    batch_id TEXT,
                    target_item_id TEXT,
                    action TEXT NOT NULL,
                    title TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    FOREIGN KEY(batch_id) REFERENCES sync_batches(id),
                    FOREIGN KEY(target_item_id) REFERENCES items(id)
                );

                CREATE TABLE IF NOT EXISTS notification_log (
                    id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL,
                    trigger_key TEXT NOT NULL,
                    notified_at TEXT NOT NULL,
                    UNIQUE(item_id, trigger_key),
                    FOREIGN KEY(item_id) REFERENCES items(id)
                );
                """
            )
            self._ensure_column(db, "items", "project_id", "TEXT")
            self._ensure_column(db, "items", "parent_project_id", "TEXT")
            self._ensure_column(db, "items", "effort", "INTEGER NOT NULL DEFAULT 3")
            self._ensure_column(db, "items", "base_priority", "INTEGER")
            self._ensure_column(db, "items", "priority_reason", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(db, "items", "category", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(db, "items", "category_color", "TEXT")
            self._ensure_column(db, "items", "project_rank", "INTEGER")
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_items_project_id ON items(project_id)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_items_parent_project_id "
                "ON items(parent_project_id)"
            )
            self._backfill_project_links(db)
            self._backfill_priorities(db)
            priorities = db.execute(
                "SELECT DISTINCT priority FROM items WHERE entity_type = 'project'"
            ).fetchall()
            for row in priorities:
                self._compact_project_ranks(db, int(row["priority"]))

    @staticmethod
    def _normalize_category(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip())[:50]

    def _category_color(
        self,
        db: sqlite3.Connection,
        category: str,
        requested: Any = None,
    ) -> str | None:
        if not category:
            return None
        if requested:
            color = str(requested).upper()
            if not CATEGORY_COLOR_PATTERN.fullmatch(color):
                raise ValueError("invalid category color")
            return color
        existing = db.execute(
            """
            SELECT category_color FROM items
            WHERE entity_type = 'project'
              AND category = ?
              AND category_color IS NOT NULL
            ORDER BY updated_at DESC LIMIT 1
            """,
            (category,),
        ).fetchone()
        if existing:
            return existing["category_color"]
        index = zlib.crc32(category.encode("utf-8")) % len(CATEGORY_COLORS)
        return CATEGORY_COLORS[index]

    @staticmethod
    def _ensure_column(
        db: sqlite3.Connection, table: str, column: str, definition: str
    ) -> None:
        columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _backfill_project_links(self, db: sqlite3.Connection) -> None:
        """Link legacy items to the project created in the same sync batch."""
        rows = db.execute(
            """
            SELECT e.batch_id, e.item_id, i.entity_type
            FROM activity_events e
            JOIN items i ON i.id = e.item_id
            WHERE e.batch_id IS NOT NULL
            ORDER BY e.created_at
            """
        ).fetchall()
        batches: dict[str, dict[str, list[str]]] = {}
        for row in rows:
            bucket = batches.setdefault(row["batch_id"], {"projects": [], "items": []})
            target = bucket["projects" if row["entity_type"] == "project" else "items"]
            if row["item_id"] not in target:
                target.append(row["item_id"])
        for bucket in batches.values():
            if len(bucket["projects"]) != 1:
                continue
            project_id = bucket["projects"][0]
            for item_id in bucket["items"]:
                db.execute(
                    """
                    UPDATE items SET project_id = ?
                    WHERE id = ? AND project_id IS NULL
                    """,
                    (project_id, item_id),
                )

    def _backfill_priorities(self, db: sqlite3.Connection) -> None:
        rows = db.execute(
            """
            SELECT * FROM items
            WHERE priority_reason = ''
            ORDER BY CASE WHEN entity_type = 'project' THEN 0 ELSE 1 END, created_at
            """
        ).fetchall()
        for row in rows:
            item = dict(row)
            # Legacy rows had no effort field. Infer it from their title/details
            # instead of treating the migration default as an explicit estimate.
            item["effort"] = None
            priority, effort, reason, base_priority = self._automatic_priority(
                item,
                db,
                preserve_existing=True,
            )
            db.execute(
                """
                UPDATE items
                SET priority = ?, effort = ?, base_priority = ?, priority_reason = ?
                WHERE id = ?
                """,
                (priority, effort, base_priority, reason, item["id"]),
            )

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
            except ValueError:
                return None

    @staticmethod
    def _clamp_priority(value: Any) -> int:
        try:
            return max(0, min(3, int(value)))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _normalize_explicit_priority(value: Any) -> int:
        try:
            priority = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("priority must be an integer from 1 to 3") from exc
        if priority not in {1, 2, 3}:
            raise ValueError("priority must be an integer from 1 to 3")
        return priority

    @staticmethod
    def _normalize_project_rank(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            rank = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("project_rank must be a positive integer") from exc
        if rank < 1:
            raise ValueError("project_rank must be a positive integer")
        return rank

    def _place_project(
        self,
        db: sqlite3.Connection,
        item_id: str,
        priority: int,
        requested_rank: Any = None,
    ) -> None:
        """Place a project in a dense, one-based order within its priority level."""
        rows = db.execute(
            """
            SELECT id FROM items
            WHERE entity_type = 'project' AND priority = ? AND id != ?
            ORDER BY CASE WHEN project_rank IS NULL THEN 1 ELSE 0 END,
                     project_rank, updated_at, id
            """,
            (priority, item_id),
        ).fetchall()
        rank = self._normalize_project_rank(requested_rank)
        if rank is None:
            rank = len(rows) + 1
        rank = min(rank, len(rows) + 1)
        ordered_ids = [row["id"] for row in rows]
        ordered_ids.insert(rank - 1, item_id)
        for position, project_id in enumerate(ordered_ids, start=1):
            db.execute(
                "UPDATE items SET project_rank = ? WHERE id = ?",
                (position, project_id),
            )

    @staticmethod
    def _compact_project_ranks(db: sqlite3.Connection, priority: int) -> None:
        rows = db.execute(
            """
            SELECT id FROM items
            WHERE entity_type = 'project' AND priority = ?
            ORDER BY CASE WHEN project_rank IS NULL THEN 1 ELSE 0 END,
                     project_rank, updated_at, id
            """,
            (priority,),
        ).fetchall()
        for position, row in enumerate(rows, start=1):
            db.execute(
                "UPDATE items SET project_rank = ? WHERE id = ?",
                (position, row["id"]),
            )

    def _infer_effort(self, item: dict[str, Any]) -> int:
        if item.get("effort") is not None:
            try:
                return max(1, min(5, int(item["effort"])))
            except (TypeError, ValueError):
                pass
        text = f"{item.get('title', '')}\n{item.get('details', '')}"
        if EFFORT_EASY_PATTERN.search(text):
            return 1
        if EFFORT_HARD_PATTERN.search(text):
            return 4
        return 3

    @staticmethod
    def _priority_from_project_overview(item: dict[str, Any]) -> int | None:
        text = f"{item.get('title', '')}\n{item.get('details', '')}"
        if "最優先" in text:
            return 3
        match = PROJECT_RANK_PATTERN.search(text)
        if not match:
            return None
        rank = int(match.group(1))
        if rank <= 3:
            return 3
        if rank <= 5:
            return 2
        return 1

    def _automatic_priority(
        self,
        item: dict[str, Any],
        db: sqlite3.Connection,
        *,
        preserve_existing: bool = False,
    ) -> tuple[int, int, str, int | None]:
        effort = self._infer_effort(item)
        entity_type = item.get("entity_type", "task")
        existing = self._clamp_priority(item.get("priority"))
        project_id = item.get("project_id")
        stored_base = item.get("base_priority")
        stored_base = (
            self._clamp_priority(stored_base) if stored_base is not None else None
        )

        if entity_type == "project":
            overview_priority = self._priority_from_project_overview(item)
            base = existing or overview_priority or 2
            basis_to_store: int | None = base
            reason_parts = [
                (
                    f"プロジェクト概要基準 {base}"
                    if not existing and overview_priority
                    else f"プロジェクト基準 {base}"
                )
            ]
        elif item.get("_priority_explicit") and existing:
            base = existing
            basis_to_store = base
            reason_parts = [f"明示された基準 {base}"]
        elif preserve_existing and existing:
            base = existing
            basis_to_store = base
            reason_parts = [f"過去セッション基準 {base}"]
        elif stored_base:
            base = stored_base
            basis_to_store = base
            reason_parts = [f"登録時基準 {base}"]
        else:
            project = None
            if project_id:
                project = db.execute(
                    "SELECT title, priority FROM items "
                    "WHERE id = ? AND entity_type = 'project'",
                    (project_id,),
                ).fetchone()
            if project:
                base = self._clamp_priority(project["priority"]) or 1
                basis_to_store = None
                reason_parts = [f"「{project['title']}」基準 {base}"]
            else:
                base = 2
                basis_to_store = base
                reason_parts = ["所属未設定の標準基準 2"]

        adjustment = 0
        due_date = self._parse_date(item.get("due_at"))
        scheduled_date = self._parse_date(item.get("scheduled_at"))
        target_date = due_date or scheduled_date
        if (
            entity_type != "project"
            and target_date
            and item.get("status") not in {"done", "cancelled"}
        ):
            days = (target_date - date.today()).days
            if days <= 2:
                adjustment += 1
                reason_parts.append("期限・予定が2日以内 +1")
            elif days <= 7:
                adjustment += 1
                reason_parts.append("期限・予定が7日以内 +1")

        if entity_type != "project" and effort <= 2:
            adjustment += 1
            reason_parts.append(f"低工数({effort}/5) +1")
        elif entity_type != "project" and effort >= 4:
            adjustment -= 1
            reason_parts.append(f"高工数({effort}/5) -1")

        if entity_type == "project" and preserve_existing:
            priority = base
        else:
            priority = max(1, min(3, base + adjustment))
        if item.get("status") == "cancelled":
            priority = 0
            reason_parts.append("取消済み 0")
        return priority, effort, " / ".join(reason_parts), basis_to_store

    def _resolve_project_id(
        self,
        db: sqlite3.Connection,
        payload: dict[str, Any],
        batch_id: str | None,
    ) -> str | None:
        project_id = payload.get("project_id")
        if project_id:
            row = db.execute(
                "SELECT id FROM items WHERE id = ? AND entity_type = 'project'",
                (project_id,),
            ).fetchone()
            if row:
                return row["id"]
        project_title = str(payload.get("project_title") or "").strip()
        if project_title:
            row = db.execute(
                """
                SELECT id FROM items
                WHERE entity_type = 'project' AND normalized_title = ?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (normalize_title(project_title),),
            ).fetchone()
            if row:
                return row["id"]
        if batch_id:
            row = db.execute(
                """
                SELECT i.id
                FROM activity_events e
                JOIN items i ON i.id = e.item_id
                WHERE e.batch_id = ? AND i.entity_type = 'project'
                ORDER BY e.created_at DESC LIMIT 1
                """,
                (batch_id,),
            ).fetchone()
            if row:
                return row["id"]
        return None

    def create_item(self, payload: dict[str, Any], batch_id: str | None = None) -> dict[str, Any]:
        validate_text_integrity(payload)
        now = utc_now()
        item_id = payload.get("id") or str(uuid.uuid4())
        entity_type = payload.get("entity_type", "task")
        if entity_type not in VALID_TYPES:
            entity_type = "task"
        status = payload.get("status", "inbox")
        if status not in VALID_STATUSES:
            status = "inbox"
        title = str(payload.get("title", "")).strip()
        if not title:
            raise ValueError("title is required")
        if payload.get("priority") is not None:
            payload = {
                **payload,
                "priority": self._normalize_explicit_priority(payload["priority"]),
            }
        with self.connect() as db:
            category = (
                self._normalize_category(payload.get("category"))
                if entity_type == "project"
                else ""
            )
            category_color = self._category_color(
                db, category, payload.get("category_color")
            )
            project_id = (
                None
                if entity_type == "project"
                else self._resolve_project_id(db, payload, batch_id)
            )
            parent_project_id = payload.get("parent_project_id")
            if entity_type != "project":
                parent_project_id = None
            elif parent_project_id:
                parent = db.execute(
                    "SELECT id FROM items WHERE id = ? AND entity_type = 'project'",
                    (parent_project_id,),
                ).fetchone()
                parent_project_id = (
                    parent["id"] if parent and parent["id"] != item_id else None
                )
            priority, effort, priority_reason, base_priority = self._automatic_priority(
                {
                    **payload,
                    "entity_type": entity_type,
                    "status": status,
                    "project_id": project_id,
                    "priority": (
                        payload.get("priority")
                        if payload.get("priority") is not None
                        else 0
                    ),
                    "_priority_explicit": payload.get("priority") is not None,
                },
                db,
            )
            db.execute(
                """
                INSERT INTO items (
                    id, entity_type, title, normalized_title, details, status,
                    due_at, scheduled_at, priority, confidence, created_at, updated_at,
                    project_id, parent_project_id, effort, base_priority, priority_reason,
                    category, category_color, project_rank
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    entity_type,
                    title,
                    normalize_title(title),
                    str(payload.get("details") or ""),
                    status,
                    payload.get("due_at"),
                    payload.get("scheduled_at"),
                    priority,
                    float(payload.get("confidence") or 1.0),
                    now,
                    now,
                    project_id,
                    parent_project_id,
                    effort,
                    base_priority,
                    priority_reason,
                    category,
                    category_color,
                    None,
                ),
            )
            if entity_type == "project":
                self._place_project(
                    db, item_id, priority, payload.get("project_rank")
                )
            self._record_event(db, batch_id, "create", item_id, payload)
        return self.get_item(item_id)

    def get_item(self, item_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if not row:
            raise KeyError(item_id)
        return dict(row)

    def list_items(self, view: str = "all") -> list[dict[str, Any]]:
        clauses = {
            "today": """
                i.status NOT IN ('done', 'cancelled') AND
                (i.status = 'today' OR date(i.due_at) <= date('now', 'localtime')
                 OR date(i.scheduled_at) <= date('now', 'localtime'))
            """,
            "next": "i.status IN ('inbox', 'next')",
            "waiting": "i.status = 'waiting'",
            "someday": "i.status = 'someday'",
            "done": "i.status IN ('done', 'cancelled')",
            "projects": "i.entity_type = 'project' AND i.status NOT IN ('done', 'cancelled')",
            "project_tasks": "i.entity_type != 'project' AND i.project_id IS NOT NULL",
            "all": "1 = 1",
        }
        if view == "review":
            return self.list_reviews()
        where = clauses.get(view, clauses["all"])
        with self.connect() as db:
            rows = db.execute(
                f"""
                SELECT i.*, p.title AS project_title,
                       p.category AS project_category,
                       p.category_color AS project_category_color,
                       parent.title AS parent_project_title
                FROM items i
                LEFT JOIN items p ON p.id = i.project_id
                LEFT JOIN items parent ON parent.id = i.parent_project_id
                WHERE {where}
                ORDER BY
                  CASE WHEN i.entity_type = 'project' THEN 0 ELSE 1 END,
                  i.priority DESC,
                  CASE WHEN i.project_rank IS NULL THEN 1 ELSE 0 END,
                  i.project_rank,
                  CASE i.status WHEN 'today' THEN 0 WHEN 'next' THEN 1
                    WHEN 'inbox' THEN 2 WHEN 'waiting' THEN 3 ELSE 4 END,
                  CASE WHEN i.due_at IS NULL THEN 1 ELSE 0 END,
                  i.due_at, i.updated_at DESC
                """
            ).fetchall()
        items = [dict(row) for row in rows]
        if view == "projects":
            self._attach_project_roots(items)
        return items

    @staticmethod
    def _attach_project_roots(items: list[dict[str, Any]]) -> None:
        by_id = {item["id"]: item for item in items}
        for item in items:
            current = item
            seen: set[str] = set()
            while current.get("parent_project_id") in by_id:
                if current["id"] in seen:
                    break
                seen.add(current["id"])
                current = by_id[current["parent_project_id"]]
            item["root_project_id"] = current["id"]
            item["root_project_title"] = current["title"]

    def search_items(self, query: str) -> list[dict[str, Any]]:
        words = [word for word in re.split(r"\s+", query.strip()) if word]
        if not words:
            return self.list_items("all")
        where = " AND ".join("(title LIKE ? OR details LIKE ?)" for _ in words)
        params: list[str] = []
        for word in words:
            params.extend((f"%{word}%", f"%{word}%"))
        with self.connect() as db:
            rows = db.execute(
                f"""
                SELECT i.*, p.title AS project_title,
                       p.category AS project_category,
                       p.category_color AS project_category_color
                FROM items i
                LEFT JOIN items p ON p.id = i.project_id
                WHERE {where.replace("title", "i.title").replace("details", "i.details")}
                ORDER BY i.updated_at DESC
                LIMIT 100
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def list_history(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT e.*, i.title
                FROM activity_events e
                LEFT JOIN items i ON i.id = e.item_id
                ORDER BY e.created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def counts(self) -> dict[str, int]:
        return {
            "today": len(self.list_items("today")),
            "next": len(self.list_items("next")),
            "waiting": len(self.list_items("waiting")),
            "someday": len(self.list_items("someday")),
            "review": len(self.list_reviews()),
            "projects": len(self.list_items("projects")),
        }

    def sync(self, payload: dict[str, Any]) -> dict[str, Any]:
        validate_text_integrity(payload)
        idempotency_key = payload.get("idempotency_key")
        if idempotency_key:
            with self.connect() as db:
                existing = db.execute(
                    "SELECT id FROM sync_batches WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
            if existing:
                return {
                    "batch_id": existing["id"],
                    "duplicate": True,
                    "created": 0,
                    "updated": 0,
                    "review": 0,
                }

        batch_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO sync_batches
                    (id, idempotency_key, source, source_summary, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    idempotency_key,
                    payload.get("source", "chatgpt"),
                    payload.get("source_summary", ""),
                    utc_now(),
                ),
            )

        result = {"batch_id": batch_id, "duplicate": False, "created": 0, "updated": 0, "review": 0}
        for event in payload.get("events", []):
            outcome = self._apply_event(batch_id, event)
            result[outcome] += 1
        return result

    def _find_target(self, event: dict[str, Any]) -> dict[str, Any] | None:
        target_id = event.get("target_id")
        with self.connect() as db:
            if target_id:
                row = db.execute("SELECT * FROM items WHERE id = ?", (target_id,)).fetchone()
                return dict(row) if row else None
            title = str(event.get("title", "")).strip()
            if not title:
                return None
            row = db.execute(
                """
                SELECT * FROM items
                WHERE entity_type = ? AND normalized_title = ?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (event.get("entity_type", "task"), normalize_title(title)),
            ).fetchone()
            return dict(row) if row else None

    def _apply_event(self, batch_id: str, event: dict[str, Any], force: bool = False) -> str:
        action = event.get("action", "create")
        confidence = float(event.get("confidence") or 0.0)
        target = self._find_target(event)
        risky_update = action == "update" and any(
            key in event for key in ("due_at", "scheduled_at", "status")
        )
        if not force and (action in DESTRUCTIVE_ACTIONS or risky_update) and confidence < 0.90:
            self._queue_review(batch_id, event, target, "重要な状態変更の確信度が90%未満です")
            return "review"

        if action == "create" and target:
            event = {**event, "action": "note"}
            action = "note"

        if action == "create" or not target:
            self.create_item(event, batch_id)
            return "created"

        now = utc_now()
        item_id = target["id"]
        updates: dict[str, Any] = {}
        if action in {"update", "note"}:
            for key in (
                "title",
                "details",
                "due_at",
                "scheduled_at",
                "priority",
                "status",
                "effort",
                "project_id",
                "parent_project_id",
                "category",
                "category_color",
                "project_rank",
            ):
                if key in event and event[key] is not None:
                    updates[key] = event[key]
            if "project_rank" in updates:
                updates["project_rank"] = self._normalize_project_rank(
                    updates["project_rank"]
                )
            if "priority" in updates:
                updates["priority"] = self._normalize_explicit_priority(
                    updates["priority"]
                )
            if "project_title" in event and "project_id" not in updates:
                with self.connect() as lookup:
                    resolved_project = self._resolve_project_id(lookup, event, batch_id)
                if resolved_project:
                    updates["project_id"] = resolved_project
            if action == "note" and event.get("details"):
                old = target.get("details") or ""
                addition = str(event["details"]).strip()
                updates["details"] = addition if not old else f"{old}\n\n{addition}"
        elif action == "complete":
            updates["status"] = "done"
        elif action == "cancel":
            updates["status"] = "cancelled"
        elif action == "defer":
            updates["status"] = event.get("status", "someday")

        if not updates:
            updates["details"] = target.get("details", "")
        updates["updated_at"] = now
        if "title" in updates:
            updates["normalized_title"] = normalize_title(str(updates["title"]))
        columns = ", ".join(f"{key} = ?" for key in updates)
        with self.connect() as db:
            if target["entity_type"] == "project" and (
                "category" in updates or "category_color" in updates
            ):
                category = self._normalize_category(
                    updates.get("category", target.get("category"))
                )
                requested_color = (
                    updates.get("category_color")
                    if "category_color" in updates
                    else (
                        target.get("category_color")
                        if category == target.get("category")
                        else None
                    )
                )
                updates["category"] = category
                updates["category_color"] = self._category_color(
                    db, category, requested_color
                )
                columns = ", ".join(f"{key} = ?" for key in updates)
            db.execute(
                f"UPDATE items SET {columns} WHERE id = ?",
                (*updates.values(), item_id),
            )
            if target["entity_type"] == "project" and updates.get("category"):
                db.execute(
                    """
                    UPDATE items
                    SET category_color = ?, updated_at = ?
                    WHERE entity_type = 'project' AND category = ? AND id != ?
                    """,
                    (
                        updates["category_color"],
                        now,
                        updates["category"],
                        item_id,
                    ),
                )
            refreshed = dict(
                db.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
            )
            priority, effort, reason, base_priority = self._automatic_priority(
                {
                    **refreshed,
                    "_priority_explicit": event.get("priority") is not None,
                },
                db,
            )
            db.execute(
                """
                UPDATE items
                SET priority = ?, effort = ?, base_priority = ?, priority_reason = ?
                WHERE id = ?
                """,
                (priority, effort, base_priority, reason, item_id),
            )
            if target["entity_type"] == "project":
                if int(target.get("priority") or 0) != priority:
                    self._compact_project_ranks(
                        db, int(target.get("priority") or 0)
                    )
                self._place_project(
                    db,
                    item_id,
                    priority,
                    event.get("project_rank", refreshed.get("project_rank")),
                )
            self._record_event(db, batch_id, action, item_id, event)
        return "updated"

    def _queue_review(
        self,
        batch_id: str,
        event: dict[str, Any],
        target: dict[str, Any] | None,
        reason: str,
    ) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO review_queue (
                    id, batch_id, target_item_id, action, title, reason,
                    payload_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    str(uuid.uuid4()),
                    batch_id,
                    target["id"] if target else None,
                    event.get("action", "update"),
                    event.get("title") or (target or {}).get("title") or "名称未設定",
                    reason,
                    json.dumps(event, ensure_ascii=False),
                    utc_now(),
                ),
            )

    def list_reviews(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT * FROM review_queue
                WHERE status = 'pending'
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def resolve_review(self, review_id: str, approve: bool) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM review_queue WHERE id = ? AND status = 'pending'",
                (review_id,),
            ).fetchone()
        if not row:
            raise KeyError(review_id)
        record = dict(row)
        if approve:
            event = json.loads(record["payload_json"])
            self._apply_event(record["batch_id"], event, force=True)
        with self.connect() as db:
            db.execute(
                """
                UPDATE review_queue SET status = ?, resolved_at = ?
                WHERE id = ?
                """,
                ("approved" if approve else "rejected", utc_now(), review_id),
            )
        return {"id": review_id, "status": "approved" if approve else "rejected"}

    def update_status(self, item_id: str, status: str) -> dict[str, Any]:
        if status not in VALID_STATUSES:
            raise ValueError("invalid status")
        with self.connect() as db:
            db.execute(
                "UPDATE items SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), item_id),
            )
            self._refresh_priority(db, item_id)
            self._record_event(db, None, "manual_update", item_id, {"status": status})
        return self.get_item(item_id)

    def update_item(self, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        validate_text_integrity(payload)
        allowed = {
            "title",
            "details",
            "due_at",
            "scheduled_at",
            "priority",
            "status",
            "entity_type",
            "effort",
            "project_id",
            "parent_project_id",
            "category",
            "category_color",
            "project_rank",
        }
        updates = {key: value for key, value in payload.items() if key in allowed}
        if not updates:
            return self.get_item(item_id)
        if "status" in updates and updates["status"] not in VALID_STATUSES:
            raise ValueError("invalid status")
        if "entity_type" in updates and updates["entity_type"] not in VALID_TYPES:
            raise ValueError("invalid entity type")
        if "effort" in updates:
            updates["effort"] = max(1, min(5, int(updates["effort"])))
        if "priority" in updates:
            updates["priority"] = self._normalize_explicit_priority(
                updates["priority"]
            )
        if "project_rank" in updates:
            updates["project_rank"] = self._normalize_project_rank(
                updates["project_rank"]
            )
        if "title" in updates:
            title = str(updates["title"]).strip()
            if not title:
                raise ValueError("title is required")
            updates["title"] = title
            updates["normalized_title"] = normalize_title(title)
        updates["updated_at"] = utc_now()
        columns = ", ".join(f"{key} = ?" for key in updates)
        with self.connect() as db:
            current = db.execute(
                "SELECT * FROM items WHERE id = ?", (item_id,)
            ).fetchone()
            if not current:
                raise KeyError(item_id)
            resulting_type = updates.get("entity_type", current["entity_type"])
            old_priority = int(current["priority"] or 0)
            if resulting_type == "project":
                category = self._normalize_category(
                    updates.get("category", current["category"])
                )
                requested_color = (
                    updates.get("category_color")
                    if "category_color" in updates
                    else (
                        current["category_color"]
                        if category == current["category"]
                        else None
                    )
                )
                updates["category"] = category
                updates["category_color"] = self._category_color(
                    db, category, requested_color
                )
            else:
                updates["category"] = ""
                updates["category_color"] = None
            if updates.get("project_id"):
                project = db.execute(
                    "SELECT id FROM items WHERE id = ? AND entity_type = 'project'",
                    (updates["project_id"],),
                ).fetchone()
                if not project:
                    raise ValueError("invalid project")
            if updates.get("parent_project_id"):
                parent = db.execute(
                    """
                    SELECT id, parent_project_id FROM items
                    WHERE id = ? AND entity_type = 'project'
                    """,
                    (updates["parent_project_id"],),
                ).fetchone()
                if not parent or updates["parent_project_id"] == item_id:
                    raise ValueError("invalid parent project")
                ancestor = parent
                seen: set[str] = set()
                while ancestor and ancestor["id"] not in seen:
                    if ancestor["id"] == item_id:
                        raise ValueError("parent project would create a cycle")
                    seen.add(ancestor["id"])
                    parent_id = ancestor["parent_project_id"]
                    ancestor = (
                        db.execute(
                            "SELECT id, parent_project_id FROM items WHERE id = ?",
                            (parent_id,),
                        ).fetchone()
                        if parent_id
                        else None
                    )
            if resulting_type != "project":
                updates["parent_project_id"] = None
                updates["project_rank"] = None
            if resulting_type == "project":
                updates["project_id"] = None
            columns = ", ".join(f"{key} = ?" for key in updates)
            cursor = db.execute(
                f"UPDATE items SET {columns} WHERE id = ?",
                (*updates.values(), item_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(item_id)
            if resulting_type == "project" and updates.get("category"):
                db.execute(
                    """
                    UPDATE items
                    SET category_color = ?, updated_at = ?
                    WHERE entity_type = 'project' AND category = ? AND id != ?
                    """,
                    (
                        updates["category_color"],
                        updates["updated_at"],
                        updates["category"],
                        item_id,
                    ),
                )
            self._refresh_priority(
                db,
                item_id,
                priority_explicit="priority" in payload,
            )
            if resulting_type == "project":
                refreshed_project = db.execute(
                    "SELECT priority, project_rank FROM items WHERE id = ?",
                    (item_id,),
                ).fetchone()
                if old_priority != refreshed_project["priority"]:
                    self._compact_project_ranks(db, old_priority)
                self._place_project(
                    db,
                    item_id,
                    int(refreshed_project["priority"]),
                    (
                        payload.get("project_rank")
                        if "project_rank" in payload
                        else refreshed_project["project_rank"]
                    ),
                )
                child_rows = db.execute(
                    "SELECT id FROM items WHERE project_id = ?", (item_id,)
                ).fetchall()
                for child in child_rows:
                    self._refresh_priority(db, child["id"])
            self._record_event(db, None, "manual_update", item_id, payload)
        return self.get_item(item_id)

    def _refresh_priority(
        self,
        db: sqlite3.Connection,
        item_id: str,
        *,
        priority_explicit: bool = False,
    ) -> None:
        row = db.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if not row:
            raise KeyError(item_id)
        priority, effort, reason, base_priority = self._automatic_priority(
            {**dict(row), "_priority_explicit": priority_explicit},
            db,
        )
        db.execute(
            """
            UPDATE items
            SET priority = ?, effort = ?, base_priority = ?, priority_reason = ?
            WHERE id = ?
            """,
            (priority, effort, base_priority, reason, item_id),
        )

    def apply_automatic_rules(self) -> int:
        now = utc_now()
        changed = 0
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT id FROM items
                WHERE status IN ('inbox', 'next')
                  AND (
                    date(due_at) <= date('now', 'localtime')
                    OR date(scheduled_at) <= date('now', 'localtime')
                  )
                """
            ).fetchall()
            for row in rows:
                db.execute(
                    "UPDATE items SET status = 'today', updated_at = ? WHERE id = ?",
                    (now, row["id"]),
                )
                self._record_event(
                    db,
                    None,
                    "auto_promote",
                    row["id"],
                    {"status": "today", "reason": "期限または予定日が到来"},
                )
                changed += 1
            priority_rows = db.execute(
                """
                SELECT id FROM items
                WHERE entity_type != 'project'
                  AND status NOT IN ('done', 'cancelled')
                """
            ).fetchall()
            for row in priority_rows:
                self._refresh_priority(db, row["id"])
        return changed

    def backup(self, destination: str | Path) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        source = sqlite3.connect(self.path)
        copy = sqlite3.connect(target)
        try:
            source.backup(copy)
        finally:
            copy.close()
            source.close()
        return target

    def export_json(self, destination: str | Path) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "exported_at": utc_now(),
            "version": 1,
            "items": self.list_items("all"),
            "history": self.list_history(limit=10000),
            "pending_reviews": self.list_reviews(),
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def change_token(self) -> int:
        """Return a cheap, monotonic token for changes visible in the UI."""
        with self.connect() as db:
            row = db.execute(
                "SELECT COALESCE(MAX(rowid), 0) AS token FROM activity_events"
            ).fetchone()
        return int(row["token"])

    def due_notifications(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT i.*,
                  COALESCE(i.scheduled_at, i.due_at) AS trigger_key
                FROM items i
                WHERE i.status NOT IN ('done', 'cancelled')
                  AND COALESCE(i.scheduled_at, i.due_at) IS NOT NULL
                  AND datetime(COALESCE(i.scheduled_at, i.due_at))
                      <= datetime('now', 'localtime')
                  AND NOT EXISTS (
                    SELECT 1 FROM notification_log n
                    WHERE n.item_id = i.id
                      AND n.trigger_key = COALESCE(i.scheduled_at, i.due_at)
                  )
                ORDER BY COALESCE(i.scheduled_at, i.due_at)
                LIMIT 5
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_notified(self, item_id: str, trigger_key: str) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT OR IGNORE INTO notification_log
                    (id, item_id, trigger_key, notified_at)
                VALUES (?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), item_id, trigger_key, utc_now()),
            )

    @staticmethod
    def _record_event(
        db: sqlite3.Connection,
        batch_id: str | None,
        action: str,
        item_id: str | None,
        payload: dict[str, Any],
    ) -> None:
        db.execute(
            """
            INSERT INTO activity_events (
                id, batch_id, action, item_id, payload_json,
                source_excerpt, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                batch_id,
                action,
                item_id,
                json.dumps(payload, ensure_ascii=False),
                payload.get("source_excerpt", ""),
                utc_now(),
            ),
        )
