"""SQLite 状态层：去重、期号、订阅者、点击、账本。

单文件 SQLite 就够了，别一上来上 Postgres——50 块的机器跑不动。
"""
from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass, asdict
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    uid         TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    summary     TEXT DEFAULT '',
    engagement  REAL DEFAULT 0,
    published   INTEGER NOT NULL,
    score       REAL NOT NULL,
    first_seen  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_pub ON items(published DESC);
CREATE INDEX IF NOT EXISTS idx_items_seen ON items(first_seen DESC);

CREATE TABLE IF NOT EXISTS issues (
    issue_no    INTEGER PRIMARY KEY,
    day         TEXT NOT NULL,
    title       TEXT NOT NULL,
    free_uids   TEXT NOT NULL,
    paid_uids   TEXT NOT NULL,
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS subscribers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    contact     TEXT UNIQUE NOT NULL,
    token       TEXT NOT NULL,
    tier        TEXT DEFAULT 'free',
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS clicks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          INTEGER NOT NULL,
    uid         TEXT,
    slot        TEXT,
    target      TEXT,
    ip_hash     TEXT
);

CREATE TABLE IF NOT EXISTS ledger (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          INTEGER NOT NULL,
    kind        TEXT NOT NULL,
    amount_cny  REAL NOT NULL,
    note        TEXT DEFAULT ''
);
"""


@dataclass
class Item:
    uid: str
    source: str
    title: str
    url: str
    summary: str = ""
    engagement: float = 0.0
    published: int = 0
    score: float = 0.0
    first_seen: int = 0


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        # check_same_thread=False：http.server 是多线程的，同一个连接会被多个
        # 请求线程用；SQLite 串行化模式下这样是安全的（写入量极小）。
        self.conn = sqlite3.connect(self.path, check_same_thread=False, timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    # ---------- items ----------
    def seen(self, uid: str) -> bool:
        row = self.conn.execute("SELECT 1 FROM items WHERE uid=?", (uid,)).fetchone()
        return row is not None

    def recent_titles(self, limit: int = 400) -> list[str]:
        rows = self.conn.execute(
            "SELECT title FROM items ORDER BY first_seen DESC LIMIT ?", (limit,)
        ).fetchall()
        return [r["title"] for r in rows]

    def upsert_item(self, it: Item) -> None:
        self.conn.execute(
            """INSERT INTO items(uid,source,title,url,summary,engagement,published,score,first_seen)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(uid) DO UPDATE SET
                 engagement=excluded.engagement,
                 score=excluded.score,
                 summary=excluded.summary""",
            (it.uid, it.source, it.title, it.url, it.summary,
             it.engagement, it.published, it.score, it.first_seen or int(time.time())),
        )

    def commit(self) -> None:
        self.conn.commit()

    def get_items(self, uids: list[str]) -> list[Item]:
        if not uids:
            return []
        q = ",".join("?" * len(uids))
        rows = self.conn.execute(f"SELECT * FROM items WHERE uid IN ({q})", uids).fetchall()
        by_uid = {r["uid"]: Item(**{k: r[k] for k in r.keys()}) for r in rows}
        return [by_uid[u] for u in uids if u in by_uid]

    # ---------- issues ----------
    def next_issue_no(self) -> int:
        row = self.conn.execute("SELECT COALESCE(MAX(issue_no),0)+1 AS n FROM issues").fetchone()
        return int(row["n"])

    def save_issue(self, issue_no: int, day: str, title: str,
                   free_uids: list[str], paid_uids: list[str]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO issues(issue_no,day,title,free_uids,paid_uids,created_at)"
            " VALUES(?,?,?,?,?,?)",
            (issue_no, day, title, ",".join(free_uids), ",".join(paid_uids), int(time.time())),
        )
        self.conn.commit()

    def list_issues(self, limit: int = 30) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM issues ORDER BY issue_no DESC LIMIT ?", (limit,)
        ).fetchall()

    # ---------- subscribers ----------
    def add_subscriber(self, contact: str, tier: str = "free") -> str:
        contact = contact.strip().lower()
        token = hashlib.sha256(f"{contact}:{time.time()}:{self.path}".encode()).hexdigest()[:24]
        self.conn.execute(
            "INSERT INTO subscribers(contact,token,tier,created_at) VALUES(?,?,?,?)"
            " ON CONFLICT(contact) DO UPDATE SET tier=excluded.tier",
            (contact, token, tier, int(time.time())),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT token FROM subscribers WHERE contact=?", (contact,)).fetchone()
        return row["token"]

    def subscriber_by_token(self, token: str):
        return self.conn.execute(
            "SELECT * FROM subscribers WHERE token=?", (token,)
        ).fetchone()

    def paid_subscribers(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM subscribers WHERE tier='paid'"
        ).fetchall()

    # ---------- clicks / money ----------
    def log_click(self, uid: str | None, slot: str, target: str, ip_hash: str = "") -> None:
        self.conn.execute(
            "INSERT INTO clicks(ts,uid,slot,target,ip_hash) VALUES(?,?,?,?,?)",
            (int(time.time()), uid, slot, target, ip_hash),
        )
        self.conn.commit()

    def add_revenue(self, amount: float, kind: str, note: str = "") -> None:
        self.conn.execute(
            "INSERT INTO ledger(ts,kind,amount_cny,note) VALUES(?,?,?,?)",
            (int(time.time()), kind, amount, note),
        )
        self.conn.commit()

    def stats(self) -> dict:
        c = self.conn
        return {
            "items": c.execute("SELECT COUNT(*) n FROM items").fetchone()["n"],
            "issues": c.execute("SELECT COUNT(*) n FROM issues").fetchone()["n"],
            "subscribers": c.execute("SELECT COUNT(*) n FROM subscribers").fetchone()["n"],
            "paid_subscribers": c.execute(
                "SELECT COUNT(*) n FROM subscribers WHERE tier='paid'").fetchone()["n"],
            "clicks": c.execute("SELECT COUNT(*) n FROM clicks").fetchone()["n"],
            "revenue_cny": round(c.execute(
                "SELECT COALESCE(SUM(amount_cny),0) v FROM ledger").fetchone()["v"], 2),
        }
