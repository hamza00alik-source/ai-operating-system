"""Business-unit scoped product, counterparty, and order workflow records.

These are internal owner-controlled records only. This module never contacts
customers or suppliers, moves money, reserves inventory, or fulfills orders.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4


class BusinessOperationsRepository:
    def __init__(self, db, lock):
        self._db, self._lock = db, lock
        with lock:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS opencompany_counterparties(
              id TEXT PRIMARY KEY,business_id TEXT NOT NULL,kind TEXT NOT NULL,
              name TEXT NOT NULL,country TEXT NOT NULL,reference TEXT NOT NULL,
              status TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_opencompany_counterparties_business
              ON opencompany_counterparties(business_id,kind);
            CREATE TABLE IF NOT EXISTS opencompany_products(
              id TEXT PRIMARY KEY,business_id TEXT NOT NULL,sku TEXT NOT NULL,
              name TEXT NOT NULL,description TEXT NOT NULL,unit_price_minor INTEGER NOT NULL,
              currency TEXT NOT NULL,supplier_id TEXT,status TEXT NOT NULL,
              created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
              UNIQUE(business_id,sku));
            CREATE INDEX IF NOT EXISTS idx_opencompany_products_business
              ON opencompany_products(business_id,status);
            CREATE TABLE IF NOT EXISTS opencompany_orders(
              id TEXT PRIMARY KEY,business_id TEXT NOT NULL,order_reference TEXT NOT NULL,
              customer_id TEXT NOT NULL,currency TEXT NOT NULL,total_minor INTEGER NOT NULL,
              status TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
              UNIQUE(business_id,order_reference));
            CREATE TABLE IF NOT EXISTS opencompany_order_items(
              id TEXT PRIMARY KEY,order_id TEXT NOT NULL,product_id TEXT NOT NULL,
              sku TEXT NOT NULL,product_name TEXT NOT NULL,quantity INTEGER NOT NULL,
              unit_price_minor INTEGER NOT NULL,line_total_minor INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS opencompany_order_events(
              id TEXT PRIMARY KEY,order_id TEXT NOT NULL,action TEXT NOT NULL,
              rationale TEXT NOT NULL,evidence_reference TEXT NOT NULL,created_at TEXT NOT NULL);
            """)
            db.commit()

    def create_counterparty(self, record):
        with self._lock:
            self._db.execute(
                "INSERT INTO opencompany_counterparties VALUES(?,?,?,?,?,?,?,?)",
                (record["id"], record["business_id"], record["kind"], record["name"],
                 record["country"], record["reference"], record["status"], record["created_at"]),
            )
            self._db.commit()
        return record

    def list_counterparties(self, business_id, kind=None):
        with self._lock:
            if kind:
                rows=self._db.execute(
                    "SELECT * FROM opencompany_counterparties WHERE business_id=? AND kind=? ORDER BY created_at",
                    (business_id,kind),
                ).fetchall()
            else:
                rows=self._db.execute(
                    "SELECT * FROM opencompany_counterparties WHERE business_id=? ORDER BY created_at",
                    (business_id,),
                ).fetchall()
        return [dict(row) for row in rows]

    def get_counterparty(self,business_id,counterparty_id):
        with self._lock:
            row=self._db.execute(
                "SELECT * FROM opencompany_counterparties WHERE business_id=? AND id=?",
                (business_id,str(counterparty_id)),
            ).fetchone()
        return dict(row) if row else None

    def create_product(self,record):
        with self._lock:
            self._db.execute(
                "INSERT INTO opencompany_products VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (record["id"],record["business_id"],record["sku"],record["name"],
                 record["description"],record["unit_price_minor"],record["currency"],
                 record["supplier_id"],record["status"],record["created_at"],record["updated_at"]),
            )
            self._db.commit()
        return record

    def list_products(self,business_id,status=None):
        with self._lock:
            if status:
                rows=self._db.execute(
                    "SELECT * FROM opencompany_products WHERE business_id=? AND status=? ORDER BY created_at",
                    (business_id,status),
                ).fetchall()
            else:
                rows=self._db.execute(
                    "SELECT * FROM opencompany_products WHERE business_id=? ORDER BY created_at",
                    (business_id,),
                ).fetchall()
        return [dict(row) for row in rows]

    def activate_product(self,business_id,product_id,rationale):
        now=datetime.now(timezone.utc).isoformat()
        with self._lock:
            row=self._db.execute(
                "SELECT status FROM opencompany_products WHERE business_id=? AND id=?",
                (business_id,str(product_id)),
            ).fetchone()
            if not row:return None
            if row["status"]!="draft":raise ValueError("Only draft products can be activated.")
            self._db.execute(
                "UPDATE opencompany_products SET status='active',updated_at=? WHERE business_id=? AND id=?",
                (now,business_id,str(product_id)),
            )
            self._db.commit()
        return {"product_id":str(product_id),"business_id":business_id,"status":"active",
                "rationale":rationale,"updated_at":now,"published_externally":False}

    def create_order(self,business_id,customer_id,currency,items):
        now=datetime.now(timezone.utc).isoformat()
        order_id=str(uuid4())
        reference="OC-"+order_id[:8].upper()
        normalized=[]
        total=0
        with self._lock:
            customer=self._db.execute(
                "SELECT id FROM opencompany_counterparties WHERE business_id=? AND id=? AND kind='customer' AND status='active'",
                (business_id,str(customer_id)),
            ).fetchone()
            if not customer:raise ValueError("An active customer record in this business unit is required.")
            for item in items:
                row=self._db.execute(
                    "SELECT id,sku,name,unit_price_minor,currency,status FROM opencompany_products WHERE business_id=? AND id=?",
                    (business_id,str(item["product_id"])),
                ).fetchone()
                if not row:raise ValueError("Every order product must belong to the same business unit.")
                if row["status"]!="active":raise ValueError("Only owner-activated products can be added to an order.")
                if row["currency"]!=currency:raise ValueError("All order products must use the selected currency.")
                quantity=int(item["quantity"])
                if quantity<1 or quantity>100000:raise ValueError("Order quantity is outside the supported range.")
                line_total=int(row["unit_price_minor"])*quantity
                total+=line_total
                normalized.append({
                    "id":str(uuid4()),"product_id":row["id"],"sku":row["sku"],
                    "product_name":row["name"],"quantity":quantity,
                    "unit_price_minor":int(row["unit_price_minor"]),"line_total_minor":line_total,
                })
            if not normalized:raise ValueError("An order must contain at least one product.")
            order={
                "id":order_id,"business_id":business_id,"order_reference":reference,
                "customer_id":str(customer_id),"currency":currency,"total_minor":total,
                "status":"draft","created_at":now,"updated_at":now,
            }
            self._db.execute(
                "INSERT INTO opencompany_orders VALUES(?,?,?,?,?,?,?,?,?)",
                (order_id,business_id,reference,str(customer_id),currency,total,"draft",now,now),
            )
            for line in normalized:
                self._db.execute(
                    "INSERT INTO opencompany_order_items VALUES(?,?,?,?,?,?,?,?)",
                    (line["id"],order_id,line["product_id"],line["sku"],line["product_name"],
                     line["quantity"],line["unit_price_minor"],line["line_total_minor"]),
                )
            self._db.execute(
                "INSERT INTO opencompany_order_events VALUES(?,?,?,?,?,?)",
                (str(uuid4()),order_id,"draft_created","Owner created an internal draft order.","",now),
            )
            self._db.commit()
        return {**order,"items":normalized,"customer_contacted":False,"payment_requested":False}

    def list_orders(self,business_id,status=None):
        with self._lock:
            if status:
                rows=self._db.execute(
                    "SELECT * FROM opencompany_orders WHERE business_id=? AND status=? ORDER BY created_at DESC",
                    (business_id,status),
                ).fetchall()
            else:
                rows=self._db.execute(
                    "SELECT * FROM opencompany_orders WHERE business_id=? ORDER BY created_at DESC",
                    (business_id,),
                ).fetchall()
        return [self.get_order(business_id,row["id"]) for row in rows]

    def get_order(self,business_id,order_id):
        with self._lock:
            row=self._db.execute(
                "SELECT * FROM opencompany_orders WHERE business_id=? AND id=?",
                (business_id,str(order_id)),
            ).fetchone()
            if not row:return None
            items=self._db.execute(
                "SELECT * FROM opencompany_order_items WHERE order_id=? ORDER BY rowid",
                (str(order_id),),
            ).fetchall()
            events=self._db.execute(
                "SELECT * FROM opencompany_order_events WHERE order_id=? ORDER BY created_at",
                (str(order_id),),
            ).fetchall()
        return {**dict(row),"items":[dict(x) for x in items],"events":[dict(x) for x in events],
                "customer_contacted":False,"external_payment_initiated":False}

    def transition_order(self,business_id,order_id,target,rationale,evidence_reference=""):
        allowed={
            "draft":{"owner_approved","cancelled"},
            "owner_approved":{"awaiting_payment_verification","cancelled"},
            "awaiting_payment_verification":{"payment_verified_owner_attested","cancelled"},
            "payment_verified_owner_attested":{"fulfilling"},
            "fulfilling":{"fulfilled"},
        }
        now=datetime.now(timezone.utc).isoformat()
        with self._lock:
            row=self._db.execute(
                "SELECT status FROM opencompany_orders WHERE business_id=? AND id=?",
                (business_id,str(order_id)),
            ).fetchone()
            if not row:return None
            current=row["status"]
            if target not in allowed.get(current,set()):
                raise ValueError(f"Order cannot transition from {current} to {target}.")
            if target=="payment_verified_owner_attested" and not evidence_reference.strip():
                raise ValueError("An evidence reference is required for owner-attested payment verification.")
            self._db.execute(
                "UPDATE opencompany_orders SET status=?,updated_at=? WHERE business_id=? AND id=?",
                (target,now,business_id,str(order_id)),
            )
            self._db.execute(
                "INSERT INTO opencompany_order_events VALUES(?,?,?,?,?,?)",
                (str(uuid4()),str(order_id),"status_"+target,rationale[:1200],evidence_reference[:500],now),
            )
            self._db.commit()
        return self.get_order(business_id,order_id)
