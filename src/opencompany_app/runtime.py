"""OpenCompany application runtime and shared SQLite repositories."""
from __future__ import annotations
import json, os, sqlite3, threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from opencompany_core.domain import AuditRecord, TaskState
from opencompany_core.business_assets import BusinessAssetRegistry
from opencompany_core.asset_storage import PrivateFilesystemAssetStorage
from opencompany_core.asset_scanning import ClamAVUnixSocketScanner
from opencompany_core.execution import AgentDeliverable
from opencompany_core.model_gateway import ModelGateway, ProviderUnavailable
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
    def create_work_item(self,item,audit=None):
        with self._lock:
            self._connection.execute("INSERT INTO work_items VALUES(?,?,?,?,?,?,?,?,?,?)",
              (str(item.id),item.title,item.objective,item.department,item.state.value,item.business_id,
               json.dumps([str(x) for x in item.depends_on]),str(item.assigned_agent_id) if item.assigned_agent_id else None,
               item.assigned_role_key,item.revision))
            if audit is not None:
                self._append_audit(audit)
            self._connection.commit()
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
    def get(self,key):
        return None

class DelegationRepository(SharedRepository):
    """Persist owner-reviewed delegation proposals without admitting queue work."""
    def __init__(self,db,lock):
        super().__init__(db,lock)
        with lock:
            db.execute("""CREATE TABLE IF NOT EXISTS opencompany_delegation_proposals(
              id TEXT PRIMARY KEY,work_item_id TEXT NOT NULL,status TEXT NOT NULL,
              payload TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""")
            db.commit()

    def save_proposal(self,proposal):
        payload=json.dumps(proposal,sort_keys=True)
        with self._lock:
            self._db.execute("""INSERT INTO opencompany_delegation_proposals
              (id,work_item_id,status,payload,created_at,updated_at) VALUES(?,?,?,?,?,?)
              ON CONFLICT(id) DO UPDATE SET status=excluded.status,payload=excluded.payload,
              updated_at=excluded.updated_at""",
              (proposal["id"],proposal["work_item_id"],proposal["status"],payload,
               proposal["created_at"],proposal["updated_at"]))
            self._db.commit()
        return proposal

    def get_proposal(self,work_item_id,proposal_id):
        with self._lock:
            row=self._db.execute(
                "SELECT payload FROM opencompany_delegation_proposals WHERE work_item_id=? AND id=?",
                (str(work_item_id),str(proposal_id))).fetchone()
        return json.loads(row["payload"]) if row else None

    def list_proposals(self,work_item_id):
        with self._lock:
            rows=self._db.execute(
                "SELECT payload FROM opencompany_delegation_proposals WHERE work_item_id=? ORDER BY created_at",
                (str(work_item_id),)).fetchall()
        return [json.loads(row["payload"]) for row in rows]


class LearningRepository(SharedRepository):
    """Persist review evaluations, owner-approved learning proposals, and applied notes."""
    def __init__(self,db,lock):
        super().__init__(db,lock)
        with lock:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS opencompany_evaluations(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS opencompany_learning_proposals(id TEXT PRIMARY KEY,role_key TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS opencompany_learning_notes(id TEXT PRIMARY KEY,role_key TEXT NOT NULL,payload TEXT NOT NULL);
            """)
            db.commit()

    def save_evaluation(self,evaluation):
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO opencompany_evaluations VALUES(?,?)",
                             (evaluation["id"],json.dumps(evaluation,sort_keys=True)))
            self._db.commit()
        return evaluation

    def get_evaluations(self,ids):
        result=[]
        with self._lock:
            for value in ids:
                row=self._db.execute("SELECT payload FROM opencompany_evaluations WHERE id=?",(str(value),)).fetchone()
                if row:result.append(json.loads(row["payload"]))
        return result

    def save_proposal(self,proposal):
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO opencompany_learning_proposals VALUES(?,?,?,?)",
                             (proposal["id"],proposal["role_key"],proposal["status"],json.dumps(proposal,sort_keys=True)))
            self._db.commit()
        return proposal

    def get_proposal(self,proposal_id):
        with self._lock:
            row=self._db.execute("SELECT payload FROM opencompany_learning_proposals WHERE id=?",(str(proposal_id),)).fetchone()
        return json.loads(row["payload"]) if row else None

    def add_note(self,note):
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO opencompany_learning_notes VALUES(?,?,?)",
                             (note["id"],note["role_key"],json.dumps(note,sort_keys=True)))
            self._db.commit()
        return note

    def list_notes(self,role_key):
        with self._lock:
            rows=self._db.execute("SELECT payload FROM opencompany_learning_notes WHERE role_key=? ORDER BY rowid",(role_key,)).fetchall()
        return [json.loads(row["payload"]) for row in rows]


class FinanceRepository(SharedRepository):
    """Internal finance records only; this repository cannot initiate payments."""
    def __init__(self,db,lock):
        super().__init__(db,lock)
        with lock:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS opencompany_finance_entries(
              id TEXT PRIMARY KEY,business_id TEXT NOT NULL,entry_type TEXT NOT NULL,
              amount_minor INTEGER NOT NULL,currency TEXT NOT NULL,description TEXT NOT NULL,
              recorded_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS opencompany_finance_reviews(
              id TEXT PRIMARY KEY,entry_id TEXT NOT NULL UNIQUE,action TEXT NOT NULL,
              rationale TEXT NOT NULL,created_at TEXT NOT NULL);
            """)
            db.commit()

    def create_entry(self,entry):
        with self._lock:
            self._db.execute("INSERT INTO opencompany_finance_entries VALUES(?,?,?,?,?,?,?)",
                (entry["id"],entry["business_id"],entry["entry_type"],entry["amount_minor"],
                 entry["currency"],entry["description"],entry["recorded_at"]))
            self._db.commit()
        return entry

    def get_entry(self,entry_id):
        with self._lock:
            row=self._db.execute("SELECT * FROM opencompany_finance_entries WHERE id=?",(str(entry_id),)).fetchone()
            review=self._db.execute("SELECT * FROM opencompany_finance_reviews WHERE entry_id=?",(str(entry_id),)).fetchone()
        if not row:return None
        result=dict(row)
        result["latest_review_action"]=review["action"] if review else None
        return result

    def save_review(self,review):
        with self._lock:
            try:
                self._db.execute("INSERT INTO opencompany_finance_reviews VALUES(?,?,?,?,?)",
                    (review["id"],review["entry_id"],review["action"],review["rationale"],review["created_at"]))
            except sqlite3.IntegrityError:
                return False
            self._db.commit()
        return True

    def list_entries(self,business_id=None):
        with self._lock:
            if business_id:
                rows=self._db.execute("SELECT id FROM opencompany_finance_entries WHERE business_id=? ORDER BY rowid",(business_id,)).fetchall()
            else:
                rows=self._db.execute("SELECT id FROM opencompany_finance_entries ORDER BY rowid").fetchall()
        return [self.get_entry(row["id"]) for row in rows]


class BusinessRepository(SharedRepository):
    """Business-unit scoped credential metadata, integrations, and owner-written memory."""
    def __init__(self,db,lock):
        super().__init__(db,lock)
        with lock:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS opencompany_business_credentials(
              business_id TEXT NOT NULL,credential_key TEXT NOT NULL,encrypted_secret TEXT NOT NULL,
              created_at TEXT NOT NULL,PRIMARY KEY(business_id,credential_key));
            CREATE TABLE IF NOT EXISTS opencompany_business_integrations(
              integration_id TEXT PRIMARY KEY,business_id TEXT NOT NULL,provider_key TEXT NOT NULL,
              display_name TEXT NOT NULL,credential_key TEXT NOT NULL,permissions TEXT NOT NULL,
              rationale TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS opencompany_business_integration_events(
              event_id TEXT PRIMARY KEY,integration_id TEXT NOT NULL,action TEXT NOT NULL,
              rationale TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS opencompany_business_memory(
              business_id TEXT NOT NULL,memory_key TEXT NOT NULL,revision INTEGER NOT NULL,
              category TEXT NOT NULL,content TEXT NOT NULL,source TEXT NOT NULL,
              created_at TEXT NOT NULL,active INTEGER NOT NULL,PRIMARY KEY(business_id,memory_key));
            CREATE TABLE IF NOT EXISTS opencompany_business_memory_history(
              id TEXT PRIMARY KEY,business_id TEXT NOT NULL,memory_key TEXT NOT NULL,
              revision INTEGER NOT NULL,category TEXT NOT NULL,content TEXT NOT NULL,
              source TEXT NOT NULL,created_at TEXT NOT NULL);
            """)
            db.commit()

    def put_credential(self,business_id,credential_key,encrypted_secret):
        now=datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO opencompany_business_credentials VALUES(?,?,?,?)",
                             (business_id,credential_key,encrypted_secret,now))
            self._db.commit()
        return {"business_id":business_id,"credential_key":credential_key,"created_at":now}

    def has_credential(self,business_id,credential_key):
        with self._lock:
            row=self._db.execute("SELECT 1 FROM opencompany_business_credentials WHERE business_id=? AND credential_key=?",
                                 (business_id,credential_key)).fetchone()
        return row is not None

    def list_credentials(self,business_id):
        with self._lock:
            rows=self._db.execute("SELECT business_id,credential_key,created_at FROM opencompany_business_credentials WHERE business_id=? ORDER BY created_at",
                                  (business_id,)).fetchall()
        return [dict(row) for row in rows]

    def delete_credential(self,business_id,credential_key):
        with self._lock:
            cursor=self._db.execute("DELETE FROM opencompany_business_credentials WHERE business_id=? AND credential_key=?",
                                    (business_id,credential_key))
            self._db.commit()
        return cursor.rowcount>0

    def add_integration(self,integration):
        with self._lock:
            self._db.execute("INSERT INTO opencompany_business_integrations VALUES(?,?,?,?,?,?,?,?,?)",
                (integration["integration_id"],integration["business_id"],integration["provider_key"],
                 integration["display_name"],integration["credential_key"],json.dumps(integration["permissions"]),
                 integration["rationale"],integration["status"],integration["created_at"]))
            self._db.execute("INSERT INTO opencompany_business_integration_events VALUES(?,?,?,?,?)",
                (str(uuid4()),integration["integration_id"],"registered",integration["rationale"],integration["created_at"]))
            self._db.commit()
        return integration

    def list_integrations(self,business_id):
        with self._lock:
            rows=self._db.execute("SELECT * FROM opencompany_business_integrations WHERE business_id=? ORDER BY created_at",
                                  (business_id,)).fetchall()
        return [{
            "integration_id":row["integration_id"],"business_id":row["business_id"],
            "provider_key":row["provider_key"],"display_name":row["display_name"],
            "credential_key":row["credential_key"],"permissions":json.loads(row["permissions"]),
            "rationale":row["rationale"],"status":row["status"],"created_at":row["created_at"],
            "credential_available":self.has_credential(business_id,row["credential_key"]),
        } for row in rows]

    def integration_events(self,business_id,integration_id):
        with self._lock:
            exists=self._db.execute("SELECT 1 FROM opencompany_business_integrations WHERE business_id=? AND integration_id=?",
                                    (business_id,integration_id)).fetchone()
            if not exists:return None
            rows=self._db.execute("SELECT action,rationale,created_at FROM opencompany_business_integration_events WHERE integration_id=? ORDER BY rowid",
                                  (integration_id,)).fetchall()
        return [dict(row) for row in rows]

    def save_memory(self,business_id,memory):
        now=datetime.now(timezone.utc).isoformat()
        with self._lock:
            row=self._db.execute("SELECT revision FROM opencompany_business_memory WHERE business_id=? AND memory_key=?",
                                 (business_id,memory["memory_key"])).fetchone()
            revision=(row["revision"]+1) if row else 1
            record={**memory,"business_id":business_id,"revision":revision,"created_at":now,"active":True}
            self._db.execute("INSERT OR REPLACE INTO opencompany_business_memory VALUES(?,?,?,?,?,?,?,1)",
                (business_id,memory["memory_key"],revision,memory["category"],memory["content"],memory["source"],now))
            self._db.execute("INSERT INTO opencompany_business_memory_history VALUES(?,?,?,?,?,?,?,?)",
                (str(uuid4()),business_id,memory["memory_key"],revision,memory["category"],memory["content"],memory["source"],now))
            self._db.commit()
        return record

    def list_memory(self,business_id):
        with self._lock:
            rows=self._db.execute("SELECT * FROM opencompany_business_memory WHERE business_id=? AND active=1 ORDER BY created_at",
                                  (business_id,)).fetchall()
        return [dict(row) for row in rows]

    def memory_history(self,business_id,memory_key):
        with self._lock:
            rows=self._db.execute("SELECT * FROM opencompany_business_memory_history WHERE business_id=? AND memory_key=? ORDER BY revision",
                                  (business_id,memory_key)).fetchall()
        return [dict(row) for row in rows]

    def forget_memory(self,business_id,memory_key):
        with self._lock:
            cursor=self._db.execute("UPDATE opencompany_business_memory SET active=0 WHERE business_id=? AND memory_key=? AND active=1",
                                    (business_id,memory_key))
            self._db.commit()
        return cursor.rowcount>0


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
    def claim(self,agent_id,role_key=None):
        with self._lock:
            if role_key is None:
                row=self._db.execute("SELECT work_item_id,role_key FROM opencompany_queue WHERE agent_id=? AND state='queued' ORDER BY rowid LIMIT 1",(str(agent_id),)).fetchone()
                if row: role_key=row["role_key"]
            else:
                row=self._db.execute("SELECT work_item_id,role_key FROM opencompany_queue WHERE agent_id=? AND role_key=? AND state='queued' ORDER BY rowid LIMIT 1",(str(agent_id),role_key)).fetchone()
            if not row:return None
            self._db.execute("UPDATE opencompany_queue SET state='running' WHERE work_item_id=?",(row["work_item_id"],));self._db.commit()
            lease=QueueLease(UUID(row["work_item_id"]),agent_id,role_key,str(uuid4()));self._leases[lease.lease_id]=lease
            from dataclasses import replace
            item=self.store.get_work_item(lease.work_item_id)
            if item and item.state != TaskState.IN_PROGRESS:
                self.store.save_work_item_with_audit(replace(item,state=TaskState.IN_PROGRESS),_audit("queue.claim",item.id,"worker"))
            return lease
    def complete(self,lease):
        with self._lock:
            self._db.execute("UPDATE opencompany_queue SET state='done' WHERE work_item_id=?",(str(lease.work_item_id),));self._db.commit()
            self._leases.pop(lease.lease_id,None)
    def fail(self,lease):
        with self._lock:
            self._db.execute("UPDATE opencompany_queue SET state='failed' WHERE work_item_id=?",(str(lease.work_item_id),));self._db.commit()
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
        if not isinstance(event,dict):
            event={
                "request_id":str(uuid4()),"work_item_id":None,"role_key":None,
                "provider":getattr(event,"provider",None),"model":getattr(event,"model",None),
                "input_tokens":getattr(event,"input_tokens",0),
                "output_tokens":getattr(event,"output_tokens",0),
                "cost_usd":getattr(event,"cost_usd",0.0),
            }
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

class GatewayWorkerExecutor:
    """Generate one bounded work-item draft through the zero-cost provider gateway."""
    def __init__(self,runtime):
        self.runtime=runtime

    def execute(self,role_key,item):
        agent=next((value for value in self.runtime.agents.values()
                    if value.get("id")==str(item.assigned_agent_id)),None)
        if not agent or agent.get("state")!="active" or agent.get("role_key")!=role_key:
            raise ValueError("The assigned specialist is not active for this role.")
        if not self.runtime.gateway.eligible_providers(request_budget_usd=0.0):
            raise ProviderUnavailable("No confirmed zero-cost provider is ready.")
        capabilities=agent.get("capabilities",[])
        prompt=(
            "You are an OpenCompany specialist. Produce a useful first draft for the owner to review. "
            "Do not claim actions you did not perform. Do not contact customers, publish, spend money, "
            "change external systems, or make commitments. State assumptions and missing information. "
            "Return concise, structured Markdown.\\n\\n"
            f"Business unit: {item.business_id}\\n"
            f"Department: {item.department}\\n"
            f"Specialist role: {role_key} ({agent.get('title')})\\n"
            f"Capabilities: {', '.join(str(value) for value in capabilities)}\\n"
            f"Task: {item.title}\\nObjective: {item.objective}"
        )
        result=self.runtime.gateway.generate(
            {"task":"owner_approved_work_item_draft","prompt":prompt,
             "work_item_id":str(item.id),"role_key":role_key,"business_id":item.business_id},
            request_budget_usd=0.0,
        )
        if not isinstance(result.text,str) or not result.text.strip():
            raise ValueError("The model returned an empty specialist draft.")
        if result.cost_usd!=0.0:
            raise ProviderUnavailable("The provider violated the zero-cost policy.")
        return AgentDeliverable(
            id=uuid4(),work_item_id=item.id,role_key=role_key,content=result.text.strip(),
            provider=result.provider,model=result.model,cost_usd=result.cost_usd,
        )


class DeterministicWorker:
    def __init__(self,runtime):
        self.runtime=runtime
        self.executor=GatewayWorkerExecutor(runtime)

    def run_once(self,agent_id,role_key):
        lease=self.runtime.queue.claim(agent_id,role_key)
        if not lease:return "idle"
        item=self.runtime.store.get_work_item(lease.work_item_id)
        from dataclasses import replace
        try:
            if item is None:raise ValueError("Queued work item no longer exists.")
            deliverable=self.executor.execute(role_key,item)
            self.runtime.store.save_deliverable_with_audit(
                deliverable,_audit("worker.deliverable",item.id,"agent"))
            current=self.runtime.store.get_work_item(item.id)
            self.runtime.store.save_work_item_with_audit(
                replace(current,state=TaskState.REVIEW),
                _audit("worker.review",item.id,"worker"))
            self.runtime.queue.complete(lease)
            return "completed_review_required"
        except Exception:
            current=self.runtime.store.get_work_item(lease.work_item_id)
            if current and current.state in (TaskState.QUEUED,TaskState.IN_PROGRESS):
                self.runtime.store.save_work_item_with_audit(
                    replace(current,state=TaskState.FAILED),
                    _audit("worker.failed",current.id,"worker"))
            self.runtime.queue.fail(lease)
            raise

def _audit(action,subject_id,actor):
    return AuditRecord(uuid4(),datetime.now(timezone.utc),actor,actor,action,"work_item",str(subject_id),"recorded",str(uuid4()))

class Runtime:
    def __init__(self,database_path=":memory:"):
        self.sqlite=SQLiteStore(database_path);self.store=WorkItemRepository(self.sqlite._connection,self.sqlite._lock)
        self.delegations=DelegationRepository(self.sqlite._connection,self.sqlite._lock)
        self.sessions=SharedRepository(self.sqlite._connection,self.sqlite._lock)
        self.handoffs=SharedRepository(self.sqlite._connection,self.sqlite._lock)
        self.learning=LearningRepository(self.sqlite._connection,self.sqlite._lock)
        self.usage=UsageRepository(self.sqlite._connection,self.sqlite._lock);self.finance=FinanceRepository(self.sqlite._connection,self.sqlite._lock);self.business=BusinessRepository(self.sqlite._connection,self.sqlite._lock);self.asset_registry=BusinessAssetRegistry(self.sqlite._connection,self.sqlite._lock);self.asset_storage=None;self.asset_scanner=None
        self.queue=WorkQueue(self.sqlite._connection,self.sqlite._lock,self.store)
        self.fleet=WorkerFleet();self.gateway=ModelGateway.configure(())
        self.worker=DeterministicWorker(self);self.github_evolution=None
        self.github_evolution_tested_at=None;self.unorouter_tested_at=None
        self.provider_test_jobs={}
        self.secret_vault=SharedRepository(self.sqlite._connection,self.sqlite._lock)
        storage_root=os.getenv("OPENCOMPANY_ASSET_STORAGE_ROOT","").strip()
        scanner_socket=os.getenv("OPENCOMPANY_CLAMAV_SOCKET","").strip()
        if storage_root:
            self.asset_storage=PrivateFilesystemAssetStorage(storage_root)
        if scanner_socket:
            self.asset_scanner=ClamAVUnixSocketScanner(scanner_socket)
        self.agents={}
    def close(self):self.sqlite.close()

def create_runtime(database_path):
    return Runtime(database_path)
