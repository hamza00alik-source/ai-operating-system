"""Offline treasury records and approval primitives. No payment rails are connected."""
from __future__ import annotations
import sqlite3
import threading
from datetime import datetime, timezone
from uuid import uuid4

BUSINESSES={"physical-agency","physical-brand","digital-products"}

class TreasuryRepository:
    """Business-scoped account registry, spend approvals, and balanced journal."""

    def __init__(self, db: sqlite3.Connection, lock: threading.RLock):
        self._db,self._lock=db,lock
        with lock:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS oc_treasury_accounts(
              id TEXT PRIMARY KEY,business_id TEXT NOT NULL,name TEXT NOT NULL,
              currency TEXT NOT NULL,account_type TEXT NOT NULL,status TEXT NOT NULL,
              provider_key TEXT NOT NULL DEFAULT 'internal',masked_reference TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL,UNIQUE(business_id,name,currency));
            CREATE TABLE IF NOT EXISTS oc_treasury_spend_requests(
              id TEXT PRIMARY PRIMARY KEY,business_id TEXT NOT NULL,requester_id TEXT NOT NULL,
              payee TEXT NOT NULL,purpose TEXT NOT NULL,amount_minor INTEGER NOT NULL,
              currency TEXT NOT NULL,budget_category TEXT NOT NULL,status TEXT NOT NULL,
              approver_id TEXT,approval_note TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS oc_treasury_journal(
              id TEXT PRIMARY PRIMARY KEY,business_id TEXT NOT NULL,currency TEXT NOT NULL,
              event_type TEXT NOT NULL,reference_id TEXT NOT NULL,description TEXT NOT NULL,
              created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS oc_treasury_journal_lines(
              id TEXT PRIMARY PRIMARY KEY,journal_id TEXT NOT NULL,account_id TEXT NOT NULL,
              debit_minor INTEGER NOT NULL,credit_minor INTEGER NOT NULL);
            """.replace("TEXT PRIMARY PRIMARY KEY","TEXT PRIMARY KEY"))
            db.commit()

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _business(business_id):
        if business_id not in BUSINESSES:
            raise ValueError("Unknown business unit.")
        return business_id

    def create_account(self,business_id,name,currency,account_type="cash",provider_key="internal",masked_reference=""):
        business_id=self._business(business_id)
        name=str(name).strip();currency=str(currency).upper()
        if not name: raise ValueError("Account name is required.")
        if len(currency)!=3 or not currency.isalpha(): raise ValueError("Currency must be a 3-letter code.")
        if account_type not in ("cash","bank","wallet","clearing","revenue","expense","equity","liability"):
            raise ValueError("Unsupported account type.")
        record={"id":str(uuid4()),"business_id":business_id,"name":name,"currency":currency,
                "account_type":account_type,"status":"record_only","provider_key":str(provider_key),
                "masked_reference":str(masked_reference)[:80],"created_at":self._now()}
        with self._lock:
            self._db.execute("INSERT INTO oc_treasury_accounts VALUES(?,?,?,?,?,?,?,?,?)",
              tuple(record.values()))
            self._db.commit()
        return record

    def list_accounts(self,business_id):
        business_id=self._business(business_id)
        with self._lock:
            rows=self._db.execute("SELECT * FROM oc_treasury_accounts WHERE business_id=? ORDER BY created_at",
                                 (business_id,)).fetchall()
        return [dict(r) for r in rows]

    def submit_spend_request(self,business_id,requester_id,payee,purpose,amount_minor,currency,budget_category="general"):
        business_id=self._business(business_id)
        amount=int(amount_minor);currency=str(currency).upper()
        requester_id=str(requester_id).strip();payee=str(payee).strip();purpose=str(purpose).strip()
        if amount<=0: raise ValueError("Spend amount must be positive.")
        if len(currency)!=3 or not currency.isalpha(): raise ValueError("Currency must be a 3-letter code.")
        if not requester_id or not payee or not purpose: raise ValueError("Requester, payee, and purpose are required.")
        record={"id":str(uuid4()),"business_id":business_id,"requester_id":requester_id,
                "payee":payee[:200],"purpose":purpose[:1200],"amount_minor":amount,"currency":currency,
                "budget_category":str(budget_category)[:100],"status":"pending_approval",
                "approver_id":None,"approval_note":None,"created_at":self._now(),"updated_at":self._now()}
        with self._lock:
            self._db.execute("INSERT INTO oc_treasury_spend_requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            tuple(record.values()))
            self._db.commit()
        return record

    def get_spend_request(self,business_id,request_id):
        business_id=self._business(business_id)
        with self._lock:
            row=self._db.execute("SELECT * FROM oc_treasury_spend_requests WHERE business_id=? AND id=?",
                               (business_id,str(request_id))).fetchone()
        return dict(row) if row else None

    def list_spend_requests(self,business_id,status=None):
        business_id=self._business(business_id)
        with self._lock:
            if status:
                rows=self._db.execute("SELECT * FROM oc_treasury_spend_requests WHERE business_id=? AND status=? ORDER BY created_at",
                                    (business_id,status)).fetchall()
            else:
                rows=self._db.execute("SELECT * FROM oc_treasury_spend_requests WHERE business_id=? ORDER BY created_at",
                                    (business_id,)).fetchall()
        return [dict(r) for r in rows]

    def decide_spend_request(self,business_id,request_id,approver_id,approve,note=""):
        business_id=self._business(business_id);approver_id=str(approver_id).strip()
        note=str(note).strip()
        if not approver_id: raise ValueError("Approver identity is required.")
        with self._lock:
            row=self._db.execute("SELECT * FROM oc_treasury_spend_requests WHERE business_id=? AND id=?",
                               (business_id,str(request_id))).fetchone()
            if not row: return None
            if row["status"]!="pending_approval": raise ValueError("Only pending requests can be reviewed.")
            if approve and approver_id==row["requester_id"]:
                raise ValueError("Requesters cannot approve their own spend requests.")
            target="approved" if approve else "rejected"
            self._db.execute("UPDATE oc_treasury_spend_requests SET status=?,approver_id=?,approval_note=?,updated_at=? WHERE business_id=? AND id=?",
              (target,approver_id,note[:1200],self._now(),business_id,str(request_id)))
            self._db.commit()
        return self.get_spend_request(business_id,request_id)

    def post_journal(self,business_id,currency,event_type,reference_id,description,lines):
        """Post balanced immutable journal entry. Lines: account_id/debit_minor/credit_minor."""
        business_id=self._business(business_id);currency=str(currency).upper()
        if len(currency)!=3 or not currency.isalpha(): raise ValueError("Currency must be a 3-letter code.")
        if not lines or len(lines)<2: raise ValueError("Journal requires at least two lines.")
        normalized=[];debits=credits=0
        with self._lock:
            for line in lines:
                account=self._db.execute("SELECT business_id,currency FROM oc_treasury_accounts WHERE id=?",
                                       (str(line["account_id"]),)).fetchone()
                if not account or account["business_id"]!=business_id or account["currency"]!=currency:
                    raise ValueError("Journal account must belong to this business and currency.")
                debit=int(line.get("debit_minor",0));credit=int(line.get("credit_minor",0))
                if debit<0 or credit<0 or (debit and credit): raise ValueError("Each line must have nonnegative debit or credit, not both.")
                if debit==credit: raise ValueError("Each journal line must have exactly one nonzero side.")
                debits+=debit;credits+=credit
                normalized.append({"account_id":str(line["account_id"]),"debit_minor":debit,"credit_minor":credit})
            if debits!=credits: raise ValueError("Journal debits and credits must balance.")
            journal_id=str(uuid4());now=self._now()
            self._db.execute("INSERT INTO oc_treasury_journal VALUES(?,?,?,?,?,?,?)",
              (journal_id,business_id,currency,str(event_type)[:100],str(reference_id)[:200],str(description)[:1200],now))
            for line in normalized:
                self._db.execute("INSERT INTO oc_treasury_journal_lines VALUES(?,?,?,?,?)",
                  (str(uuid4()),journal_id,line["account_id"],line["debit_minor"],line["credit_minor"]))
            self._db.commit()
        return {"id":journal_id,"business_id":business_id,"currency":currency,"event_type":event_type,
                "reference_id":reference_id,"description":description,"total_debits_minor":debits,
                "total_credits_minor":credits,"posted":True,"funds_moved":False}

    def list_journal(self,business_id):
        business_id=self._business(business_id)
        with self._lock:
            headers=self._db.execute("SELECT * FROM oc_treasury_journal WHERE business_id=? ORDER BY created_at",
                                   (business_id,)).fetchall()
            result=[]
            for h in headers:
                lines=self._db.execute("SELECT * FROM oc_treasury_journal_lines WHERE journal_id=?",
                                      (h["id"],)).fetchall()
                result.append({**dict(h),"lines":[dict(x) for x in lines]})
        return result
