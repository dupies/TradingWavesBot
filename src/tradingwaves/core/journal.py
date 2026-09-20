"""SQLite record of every signal, decision, position and fill.

The journal is the audit trail: any trade that was or was not taken can be
explained after the fact. It is also what `Engine.reconcile` matches broker
positions against on startup.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from tradingwaves.core.models import Fill, Position, Signal
from tradingwaves.core.risk import RiskDecision

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL,
    stop_loss REAL NOT NULL,
    take_profits TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    meta TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL REFERENCES signals(id),
    approved INTEGER NOT NULL,
    lot REAL NOT NULL,
    reason TEXT,
    code TEXT
);

CREATE TABLE IF NOT EXISTS positions (
    ticket INTEGER PRIMARY KEY,
    signal_id INTEGER REFERENCES signals(id),
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    volume REAL NOT NULL,
    entry_price REAL NOT NULL,
    stop_loss REAL NOT NULL,
    take_profits TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    magic INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket INTEGER NOT NULL,
    time TEXT NOT NULL,
    price REAL NOT NULL,
    volume REAL NOT NULL,
    kind TEXT NOT NULL,
    profit REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fills_ticket ON fills(ticket);
"""


class Journal:
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def record_signal(self, signal: Signal) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO signals
                (symbol, direction, entry_price, stop_loss, take_profits, source, created_at, meta)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal.symbol,
                str(signal.direction),
                signal.entry_price,
                signal.stop_loss,
                json.dumps([asdict(tp) for tp in signal.take_profits]),
                signal.source,
                signal.created_at.isoformat(),
                json.dumps(signal.meta),
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def record_decision(self, signal_id: int, decision: RiskDecision) -> None:
        self._conn.execute(
            "INSERT INTO decisions (signal_id, approved, lot, reason, code) VALUES (?, ?, ?, ?, ?)",
            (
                signal_id,
                int(decision.approved),
                decision.lot,
                decision.reason,
                str(decision.code) if decision.code else None,
            ),
        )
        self._conn.commit()

    def record_position(self, signal_id: int | None, position: Position) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO positions
                (ticket, signal_id, symbol, direction, volume, entry_price,
                 stop_loss, take_profits, opened_at, magic)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                position.ticket,
                signal_id,
                position.symbol,
                str(position.direction),
                position.volume,
                position.entry_price,
                position.stop_loss,
                json.dumps([asdict(tp) for tp in position.take_profits]),
                position.opened_at.isoformat(),
                position.magic,
            ),
        )
        self._conn.commit()

    def record_fill(self, fill: Fill) -> None:
        self._conn.execute(
            "INSERT INTO fills (ticket, time, price, volume, kind, profit) VALUES (?, ?, ?, ?, ?, ?)",
            (
                fill.ticket,
                fill.time.isoformat(),
                fill.price,
                fill.volume,
                str(fill.kind),
                fill.profit,
            ),
        )
        self._conn.commit()

    def position_by_ticket(self, ticket: int) -> dict | None:
        row = self._conn.execute("SELECT * FROM positions WHERE ticket = ?", (ticket,)).fetchone()
        return dict(row) if row else None

    def fills_for_ticket(self, ticket: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM fills WHERE ticket = ? ORDER BY id", (ticket,)
        ).fetchall()
        return [dict(r) for r in rows]

    def rejections(self, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT d.*, s.symbol, s.source
            FROM decisions d JOIN signals s ON s.id = d.signal_id
            WHERE d.approved = 0
            ORDER BY d.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()
