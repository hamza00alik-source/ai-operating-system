"""Durable SQLite storage and append-only hash-linked event ledger."""
from __future__ import annotations
import hashlib, json, sqlite3
from pathlib import Path
from threading import RLock
from dataclasses import asdict
from opencompany.domain import Task, Opportunity, CompanyEvent


class Store:
    def __init__(self, path: str = "opencompany.sqlite"):
        self.path = path
        self.lock = RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.executescript("""
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS opportunities(id TEXT PRIMARY KEY, payload TEXT NOT NULL, score REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL, previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL);
            """)
            self.db.commit()
    def save_task(self, task: Task):
        payload=json.dumps(asdict(task), default=str, sort_keys=True)
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO tasks(id,payload) VALUES(?,?)",(str(task.id),payload));self.db.commit()
    def list_tasks(self):
        with self.lock: return [json.loads(r["payload"]) for r in self.db.execute("SELECT payload FROM tasks ORDER BY rowid")]
    def save_opportunity(self, item: Opportunity, score: float):
        payload=json.dumps(asdict(item), default=str, sort_keys=True)
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO opportunities(id,payload,score) VALUES(?,?,?)",(str(item.id),payload,score));self.db.commit()
    def list_opportunities(self):
        with self.lock: return [dict(id=r["id"],score=r["score"],opportunity=json.loads(r["payload"])) for r in self.db.execute("SELECT * FROM opportunities ORDER BY score DESC")]
    def append_event(self, event: CompanyEvent):
        payload=json.dumps(asdict(event), default=str, sort_keys=True, separators=(",",":"))
        with self.lock:
            prev=self.db.execute("SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            previous=prev["event_hash"] if prev else "0"*64
            digest=hashlib.sha256((previous+payload).encode()).hexdigest()
            self.db.execute("INSERT INTO events(id,payload,previous_hash,event_hash) VALUES(?,?,?,?)",(str(event.id),payload,previous,digest));self.db.commit()
            return digest
    def verify_event_chain(self):
        with self.lock: rows=self.db.execute("SELECT payload,previous_hash,event_hash FROM events ORDER BY seq").fetchall()
        previous="0"*64
        for row in rows:
            expected=hashlib.sha256((previous+row["payload"]).encode()).hexdigest()
            if row["previous_hash"] != previous or row["event_hash"] != expected: return False
            previous=expected
        return True
    def close(self):
        with self.lock: self.db.close()
