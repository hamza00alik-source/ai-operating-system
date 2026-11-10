"""Business-scoped department messaging and owner-supervised task delegation."""
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from ai_os.brain import BUSINESS_IDS
from ai_os.db import connect

DEPARTMENTS = {"executive","research","product","design","engineering","legal-compliance",
               "quality-assurance","marketing","sales-marketplace","customer-support","finance","people-workforce"}

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _validate_scope(business_id: str, department: str | None = None) -> None:
    if business_id not in BUSINESS_IDS:
        raise ValueError("Unknown business environment.")
    if department is not None and department not in DEPARTMENTS:
        raise ValueError("Unknown company department.")

def send_message(business_id: str, sender_department: str, recipient_department: str,
                 subject: str, body: str, related_task_id: str | None = None) -> dict:
    """Persist an internal message; no communication leaves AIOS."""
    _validate_scope(business_id, sender_department)
    _validate_scope(business_id, recipient_department)
    subject, body = (subject or "").strip(), (body or "").strip()
    if not subject or len(subject) > 200: raise ValueError("Message subject must contain 1–200 characters.")
    if not body or len(body) > 12000: raise ValueError("Message body must contain 1–12000 characters.")
    if sender_department == recipient_department: raise ValueError("Choose a different recipient department.")
    message_id, now = str(uuid4()), _now()
    with connect() as db:
        if related_task_id:
            task = db.execute("SELECT business_id FROM tasks WHERE id=?", (related_task_id,)).fetchone()
            if task is None or task["business_id"] != business_id:
                raise LookupError("Related task not found in this business environment.")
        db.execute("""INSERT INTO department_messages
            (id,business_id,sender_department,recipient_department,subject,body,related_task_id,status,created_at)
            VALUES(?,?,?,?,?,?,?,'unread',?)""",
            (message_id,business_id,sender_department,recipient_department,subject,body,related_task_id,now))
        row = db.execute("SELECT * FROM department_messages WHERE id=?", (message_id,)).fetchone()
    return dict(row)

def list_messages(business_id: str, department: str | None = None, status: str | None = None,
                  limit: int = 100) -> list[dict]:
    _validate_scope(business_id, department)
    if status not in {None,"unread","read"}: raise ValueError("Invalid message status.")
    clauses, params = ["business_id=?"], [business_id]
    if department:
        clauses.append("(recipient_department=? OR sender_department=?)")
        params.extend([department,department])
    if status:
        clauses.append("status=?")
        params.append(status)
    params.append(max(1,min(limit,200)))
    with connect() as db:
        rows = db.execute("SELECT * FROM department_messages WHERE "+" AND ".join(clauses)+
                          " ORDER BY created_at DESC LIMIT ?",params).fetchall()
    return [dict(row) for row in rows]

def mark_message_read(message_id: str, business_id: str, department: str) -> dict | None:
    _validate_scope(business_id,department)
    with connect() as db:
        cur=db.execute("""UPDATE department_messages SET status='read',read_at=?
            WHERE id=? AND business_id=? AND recipient_department=?""",
            (_now(),message_id,business_id,department))
        if not cur.rowcount: return None
        row=db.execute("SELECT * FROM department_messages WHERE id=?",(message_id,)).fetchone()
    return dict(row)

def delegate_task(business_id: str, from_department: str, to_department: str, title: str,
                  description: str, parent_task_id: str | None = None) -> dict:
    """Create and queue an internal task after an owner explicitly delegates it."""
    _validate_scope(business_id,from_department)
    _validate_scope(business_id,to_department)
    title,description=(title or "").strip(),(description or "").strip()
    if from_department==to_department: raise ValueError("Choose a different receiving department.")
    if not title or len(title)>200: raise ValueError("Delegated task title must contain 1–200 characters.")
    if len(description)>12000: raise ValueError("Delegated task description cannot exceed 12000 characters.")
    now,task_id,delegation_id=_now(),str(uuid4()),str(uuid4())
    with connect() as db:
        if parent_task_id:
            parent=db.execute("SELECT business_id,department FROM tasks WHERE id=?",(parent_task_id,)).fetchone()
            if parent is None or parent["business_id"]!=business_id:
                raise LookupError("Parent task not found in this business environment.")
            if parent["department"]!=from_department:
                raise ValueError("The parent task must belong to the delegating department.")
        db.execute("""INSERT INTO tasks(id,title,description,department,business_id,status,created_at)
            VALUES(?,?,?,?,?,'queued',?)""",(task_id,title,description,to_department,business_id,now))
        db.execute("""INSERT INTO department_delegations
            (id,business_id,parent_task_id,child_task_id,from_department,to_department,title,status,created_at)
            VALUES(?,?,?,?,?,?,?,'queued',?)""",
            (delegation_id,business_id,parent_task_id,task_id,from_department,to_department,title,now))
        message_id=str(uuid4())
        db.execute("""INSERT INTO department_messages
            (id,business_id,sender_department,recipient_department,subject,body,related_task_id,status,created_at)
            VALUES(?,?,?,?,?,?,?,'unread',?)""",
            (message_id,business_id,from_department,to_department,"Task delegated: "+title,
             description or "Please review the delegated task in the owner task queue.",task_id,now))
        row=db.execute("SELECT * FROM department_delegations WHERE id=?",(delegation_id,)).fetchone()
    # The owner explicitly submitted this delegation, so internal task execution is authorized.
    from ai_os.agent_runtime import create_run
    run = create_run(task_id)
    return {**dict(row),"message_id":message_id,"agent_run_id":run["id"],"run_status":run["status"]}

def list_delegations(business_id: str, department: str | None = None, limit: int = 100) -> list[dict]:
    _validate_scope(business_id,department)
    clauses,params=["business_id=?"],[business_id]
    if department:
        clauses.append("(from_department=? OR to_department=?)")
        params.extend([department,department])
    params.append(max(1,min(limit,200)))
    with connect() as db:
        rows=db.execute("SELECT * FROM department_delegations WHERE "+" AND ".join(clauses)+
                        " ORDER BY created_at DESC LIMIT ?",params).fetchall()
    return [dict(row) for row in rows]

def record_workflow_handoff_message(task_id: str, output: str) -> dict | None:
    """Create a recipient inbox message whenever a workflow advances to its next step."""
    with connect() as db:
        current=db.execute("""SELECT s.workflow_id,s.sequence_no,s.department,w.business_id
            FROM workflow_steps s JOIN workflow_instances w ON w.id=s.workflow_id WHERE s.task_id=?""",
            (task_id,)).fetchone()
        if current is None: return None
        following=db.execute("""SELECT task_id,department FROM workflow_steps
            WHERE workflow_id=? AND sequence_no=? AND status='queued'""",
            (current["workflow_id"],current["sequence_no"]+1)).fetchone()
    if following is None: return None
    body=("Completed department output for review and continuation:\n\n"+(output or "(No text output recorded.)"))[:12000]
    return send_message(current["business_id"],current["department"],following["department"],
                        "Workflow handoff from "+current["department"],body,following["task_id"])
