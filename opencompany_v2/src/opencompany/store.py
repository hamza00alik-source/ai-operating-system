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
            CREATE TABLE IF NOT EXISTS agent_profiles(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS agent_skill_assignments(agent_id TEXT NOT NULL, skill_key TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(agent_id,skill_key));
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

    def save_agent_profile(self, profile):
        """Persist a validated agent profile; same-ID updates are explicit."""
        from opencompany.agent import AgentProfile
        profile.validate()
        payload=json.dumps(asdict(profile), sort_keys=True, separators=(",", ":"))
        with self.lock:
            existing=self.db.execute("SELECT payload FROM agent_profiles WHERE id=?", (profile.agent_id,)).fetchone()
            if existing and existing["payload"] != payload:
                raise ValueError("Agent profile already exists; use update_agent_profile")
            self.db.execute("INSERT OR IGNORE INTO agent_profiles(id,payload) VALUES(?,?)", (profile.agent_id,payload))
            self.db.commit()
        return profile

    def update_agent_profile(self, profile):
        """Replace an existing validated profile by ID, never create implicitly."""
        from opencompany.agent import AgentProfile
        profile.validate()
        payload=json.dumps(asdict(profile), sort_keys=True, separators=(",", ":"))
        with self.lock:
            existing=self.db.execute("SELECT 1 FROM agent_profiles WHERE id=?", (profile.agent_id,)).fetchone()
            if not existing:
                raise KeyError("agent profile not found")
            self.db.execute("UPDATE agent_profiles SET payload=? WHERE id=?", (payload,profile.agent_id))
            self.db.commit()
        return profile

    def get_agent_profile(self, agent_id: str):
        from opencompany.agent import AgentProfile
        with self.lock:
            row=self.db.execute("SELECT payload FROM agent_profiles WHERE id=?", (agent_id,)).fetchone()
        if not row:
            return None
        data=json.loads(row["payload"])
        data["capabilities"]=tuple(data["capabilities"])
        data["prohibited_actions"]=tuple(data["prohibited_actions"])
        profile=AgentProfile(**data)
        return profile.validate()

    def list_agent_profiles(self):
        from opencompany.agent import AgentProfile
        with self.lock:
            rows=self.db.execute("SELECT payload FROM agent_profiles ORDER BY id").fetchall()
        profiles=[]
        for row in rows:
            data=json.loads(row["payload"])
            data["capabilities"]=tuple(data["capabilities"])
            data["prohibited_actions"]=tuple(data["prohibited_actions"])
            profiles.append(AgentProfile(**data).validate())
        return profiles

    def assign_skill(self, agent_id: str, skill):
        """Persist an explicit skill assignment after profile capability checks.

        Assignment records are metadata only; they do not create runtime handlers
        or grant permission to execute external actions.
        """
        from datetime import datetime, timezone
        skill.validate()
        profile = self.get_agent_profile(agent_id)
        if profile is None:
            raise KeyError("agent profile not found")
        missing = set(skill.required_capabilities) - set(profile.capabilities)
        if missing:
            raise ValueError("Agent lacks required skill capabilities: " + ", ".join(sorted(missing)))
        prohibited = set(profile.prohibited_actions) & set(skill.allowed_actions)
        if prohibited:
            raise ValueError("Skill includes prohibited agent actions: " + ", ".join(sorted(prohibited)))
        payload = json.dumps({
            "skill_key": skill.key,
            "skill_version": skill.version,
            "required_capabilities": list(skill.required_capabilities),
            "assigned_at": datetime.now(timezone.utc).isoformat(),
        }, sort_keys=True, separators=(",", ":"))
        with self.lock:
            existing = self.db.execute(
                "SELECT payload FROM agent_skill_assignments WHERE agent_id=? AND skill_key=?",
                (agent_id, skill.key),
            ).fetchone()
            if existing and json.loads(existing["payload"])["skill_version"] != skill.version:
                raise ValueError("Skill assignment exists at another version; unassign before reassignment")
            self.db.execute(
                "INSERT OR IGNORE INTO agent_skill_assignments(agent_id,skill_key,payload) VALUES(?,?,?)",
                (agent_id, skill.key, payload),
            )
            self.db.commit()
        return json.loads(payload)

    def list_skill_assignments(self, agent_id: str):
        with self.lock:
            rows = self.db.execute(
                "SELECT payload FROM agent_skill_assignments WHERE agent_id=? ORDER BY skill_key",
                (agent_id,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def unassign_skill(self, agent_id: str, skill_key: str):
        with self.lock:
            cursor = self.db.execute(
                "DELETE FROM agent_skill_assignments WHERE agent_id=? AND skill_key=?",
                (agent_id, skill_key),
            )
            self.db.commit()
        return cursor.rowcount == 1
