"""OpenCompany application runtime and shared SQLite repositories."""
from __future__ import annotations
import json, sqlite3, threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from opencompany_core.domain import AuditRecord, TaskState
from opencompany_core.execution import AgentDeliverable
from opencompany_core.model_gateway import ModelGateway
from opencompany_core.persistence import SQLiteStore

@dataclass(frozen=True)
class WorkItem:
    id: UUID
    title: str
    objective: str
    department: str
    state: TaskState = TaskState.PENDING
    business_id: str = "physical-agency"
    depends_on: tuple[UUID,...] = ()
    assigned_agent_id: UUID | None = None
    assigned_role_key: str | None = None
    revision: int = 1

@dataclass(frozen=True)
class QueueLease:
    work_item_id: UUID
    agent_id: UUID
    role_key: str
    lease_id: str

@dataclass(frozen=True)
class FleetStatus:
    running: bool
    worker_count: int = 0

class WorkItemRepository:
    def __init__(self, db, lock):
        self._connection,self._lock=db,lock
        with lock:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS work_items(
              id TEXT PRIMARY KEY,title TEXT NOT NULL,objective TEXT NOT NULL,department TEXT NOT NULL,
              state TEXT NOT NULL,business_id TEXT NOT NULL,depends_on TEXT NOT NULL,
              assigned_agent_id TEXT,assigned_role_key TEXT,revision INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS opencompany_deliverables(
              id TEXT PRIMARY KEY,work_item_id TEXT NOT NULL,role_key TEXT NOT NULL,content TEXT NOT NULL,
              provider TEXT NOT NULL,model TEXT NOT NULL,cost_usd REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS opencompany_audit(
              seq INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE NOT NULL,payload TEXT NOT NULL,
              previous_hash TEXT NOT NULL,event_hash TEXT NOT NULL);
            """)
            db.commit()
    @staticmethod
    def _from(row):
        if row is None:return None
        return WorkItem(UUID(row["id"]),row["title"],row["objective"],row["department"],TaskState(row["state"]),
          row["business_id"],tuple(UUID(x) for x in json.loads(row["depends_on"])),
          UUID(row["assigned_agent_id"]) if row["assigned_agent_id"] else None,row["assigned_role_key"],row["revision"])
    def get_work_item(self, item_id):
        with self._lock:
            return self._from(self._connection.execute("SELECT * FROM work_items WHERE id=?",(str(item_id),)).fetchone())
    def list_work_items(self,business_id=None):
        with self._lock:
            if business_id:
                rows=self._connection.execute("SELECT * FROM work_items WHERE business_id=? ORDER BY rowid",(business_id,)).fetchall()
            else: rows=self._connection.execute("SELECT * FROM work_items ORDER BY rowid").fetchall()
        return tuple(self._from(r) for r in rows)
    def create_work_item(self,item):
        with self._lock:
            self._connection.execute("INSERT INTO work_items VALUES(?,?,?,?,?,?,?,?,?,?)",
              (str(item.id),item.title,item.objective,item.department,item.state.value,item.business_id,
               json.dumps([str(x) for x in item.depends_on]),str(item.assigned_agent_id) if item.assigned_agent_id else None,
               item.assigned_role_key,item.revision)); self._connection.commit()
        return item
    def save_work_item_with_audit(self,item,audit):
        with self._lock:
            old=self.get_work_item(item.id)
            if old is None: raise ValueError("work item not found")
            self._connection.execute("""UPDATE work_items SET title=?,objective=?,department=?,state=?,business_id=?,
              depends_on=?,assigned_agent_id=?,assigned_role_key=?,revision=? WHERE id=?""",
              (item.title,item.objective,item.department,item.state.value,item.business_id,
               json.dumps([str(x) for x in item.depends_on]),str(item.assigned_agent_id) if item.assigned_agent_id else None,
               item.assigned_role_key,item.revision,str(item.id)))
            self._append_audit(audit); self._connection.commit()
        return True
    def save_deliverable_with_audit(self,deliverable,audit):
        with self._lock:
            self._connection.execute("INSERT INTO opencompany_deliverables VALUES(?,?,?,?,?,?,?)",
              (str(deliverable.id),str(deliverable.work_item_id),deliverable.role_key,deliverable.content,
               deliverable.provider,deliverable.model,deliverable.cost_usd))
            self._append_audit(audit); self._connection.commit()
        return True
    def list_deliverables(self,item_id):
        with self._lock:
            rows=self._connection.execute("SELECT * FROM opencompany_deliverables WHERE work_item_id=?",(str(item_id),)).fetchall()
        return tuple(dict(r) for r in rows)
    def _append_audit(self,audit):
        payload=json.dumps({"id":str(audit.id),"occurred_at":audit.occurred_at.isoformat(),"actor_type":audit.actor_type,
          "actor_id":audit.actor_id,"action":audit.action,"subject_type":audit.subject_type,"subject_id":audit.subject_id,
          "outcome":audit.outcome,"correlation_id":audit.correlation_id,"details":audit.details},sort_keys=True)
        previous=self._connection.execute("SELECT event_hash FROM opencompany_audit ORDER BY seq DESC LIMIT 1").fetchone()
        import hashlib
        prev=previous["event_hash"] if previous else "0"*64
        digest=hashlib.sha256((prev+payload).encode()).hexdigest()
        self._connection.execute("INSERT INTO opencompany_audit(event_id,payload,previous_hash,event_hash) VALUES(?,?,?,?)",
          (str(audit.id),payload,prev,digest))
    def verify_audit_chain(self):
        import hashlib
        with self._lock:
            rows=self._connection.execute("SELECT * FROM opencompany_audit ORDER BY seq").fetchall()
        prev="0"*64
        for row in rows:
            if row["previous_hash"]!=prev or hashlib.sha256((prev+row["payload"]).encode()).hexdigest()!=row["event_hash"]:return False
            prev=row["event_hash"]
        return True
    def audit_count(self):
        with self._lock:return self._connection.execute("SELECT COUNT(*) FROM opencompany_audit").fetchone()[0]

class SharedRepository:
    def __init__(self,db,lock):self._db,self._lock=db,lock

class WorkQueue(SharedRepository):
    def __init__(self,db,lock,store):
        super().__init__(db,lock); self.store=store; self._leases={}
        with lock:
            db.execute("""CREATE TABLE IF NOT EXISTS opencompany_queue(
              work_item_id TEXT PRIMARY KEY,agent_id TEXT NOT NULL,role_key TEXT NOT NULL,state TEXT NOT NULL)""");db.commit()
    def admit(self,item_id,agent_id,role_key):
        with self._lock:
            item=self.store.get_work_item(item_id)
            if not item or not item.assigned_agent_id or item.assigned_agent_id!=agent_id: raise ValueError("work must be assigned to an active agent")
            self._db.execute("INSERT OR REPLACE INTO opencompany_queue VALUES(?,?,?,'queued')",(str(item_id),str(agent_id),role_key));self._db.commit()
    def claim(self,agent_id,role_key):
        with self._lock:
            row=self._db.execute("SELECT work_item_id FROM opencompany_queue WHERE agent_id=? AND role_key=? AND state='queued' ORDER BY rowid LIMIT 1",(str(agent_id),role_key)).fetchone()
            if not row:return None
            self._db.execute("UPDATE opencompany_queue SET state='running' WHERE work_item_id=?",(row["work_item_id"],));self._db.commit()
            lease=QueueLease(UUID(row["work_item_id"]),agent_id,role_key,str(uuid4()));self._leases[lease.lease_id]=lease
            return lease
    def complete(self,lease):
        with self._lock:
            self._db.execute("UPDATE opencompany_queue SET state='done' WHERE work_item_id=?",(str(lease.work_item_id),));self._db.commit()
            self._leases.pop(lease.lease_id,None)
    def counts(self):
        with self._lock:
            rows=self._db.execute("SELECT state,COUNT(*) n FROM opencompany_queue GROUP BY state").fetchall()
        return {r["state"]:r["n"] for r in rows}
    def count(self):return sum(self.counts().values())

class WorkerFleet:
    def __init__(self):self._running=False
    def status(self):return FleetStatus(self._running,1 if self._running else 0)
    def start(self):self._running=True;return self.status()
    def stop(self):self._running=False;return self.status()

class UsageRepository(SharedRepository):
    def __init__(self,db,lock):
        super().__init__(db,lock)
        with lock:
            db.execute("""CREATE TABLE IF NOT EXISTS opencompany_usage(
              request_id TEXT PRIMARY KEY,work_item_id TEXT,role_key TEXT,provider TEXT,model TEXT,
              input_tokens INTEGER,output_tokens INTEGER,cost_usd REAL)""");db.commit()
    def record(self,event):
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO opencompany_usage VALUES(?,?,?,?,?,?,?,?)",
              tuple(event.get(k) for k in ("request_id","work_item_id","role_key","provider","model","input_tokens","output_tokens","cost_usd")))
            self._db.commit()
        return True
    def summary(self):
        with self._lock:
            rows=self._db.execute("SELECT * FROM opencompany_usage ORDER BY rowid").fetchall()
        events=[dict(r) for r in rows]
        return {"request_count":len(events),"total_cost_usd":sum(x["cost_usd"] or 0 for x in events),
          "total_input_tokens":sum(x["input_tokens"] or 0 for x in events),"total_output_tokens":sum(x["output_tokens"] or 0 for x in events),"events":events}

class DeterministicWorker:
    def __init__(self,runtime):self.runtime=runtime;self.executor=None
    def run_once(self,agent_id,role_key):
        lease=self.runtime.queue.claim(agent_id,role_key)
        if not lease:return "idle"
        item=self.runtime.store.get_work_item(lease.work_item_id)
        from dataclasses import replace
        self.runtime.store.save_work_item_with_audit(replace(item,state=TaskState.IN_PROGRESS),_audit("worker.claim",item.id,"worker"))
        deliverable=self.executor.execute(role_key,item)
        self.runtime.store.save_deliverable_with_audit(deliverable,_audit("worker.deliverable",item.id,"agent"))
        current=self.runtime.store.get_work_item(item.id)
        self.runtime.store.save_work_item_with_audit(replace(current,state=TaskState.REVIEW),_audit("worker.review",item.id,"worker"))
        self.runtime.queue.complete(lease)
        return "completed_review_required"

def _audit(action,subject_id,actor):
    return AuditRecord(uuid4(),datetime.now(timezone.utc),actor,actor,action,"work_item",str(subject_id),"recorded",str(uuid4()))

class Runtime:
    def __init__(self,database_path=":memory:"):
        self.sqlite=SQLiteStore(database_path);self.store=WorkItemRepository(self.sqlite._connection,self.sqlite._lock)
        self.delegations=SharedRepository(self.sqlite._connection,self.sqlite._lock)
        self.sessions=SharedRepository(self.sqlite._connection,self.sqlite._lock)
        self.handoffs=SharedRepository(self.sqlite._connection,self.sqlite._lock)
        self.learning=SharedRepository(self.sqlite._connection,self.sqlite._lock)
        self.usage=UsageRepository(self.sqlite._connection,self.sqlite._lock)
        self.queue=WorkQueue(self.sqlite._connection,self.sqlite._lock,self.store)
        self.fleet=WorkerFleet();self.gateway=ModelGateway.configure(())
        self.worker=DeterministicWorker(self);self.github_evolution=None
        self.github_evolution_tested_at=None;self.unorouter_tested_at=None
        self.secret_vault=SharedRepository(self.sqlite._connection,self.sqlite._lock)
        self.asset_storage=None
    def close(self):self.sqlite.close()

def create_runtime(database_path):
    return Runtime(database_path)
