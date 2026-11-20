"""Owner-controlled inventory and purchasing records; no external purchasing or payment."""
from __future__ import annotations
import json, sqlite3
from datetime import datetime, timezone
from uuid import uuid4

BUSINESSES={"physical-agency","physical-brand","digital-products"}

class InventoryOperationsRepository:
    def __init__(self, db, lock):
        self._db,self._lock=db,lock
        with lock:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS oc_inventory_balance(
              business_id TEXT NOT NULL,product_id TEXT NOT NULL,quantity_on_hand INTEGER NOT NULL DEFAULT 0,
              low_stock_threshold INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL,
              PRIMARY KEY(business_id,product_id));
            CREATE TABLE IF NOT EXISTS oc_inventory_movement(
              id TEXT PRIMARY KEY,business_id TEXT NOT NULL,product_id TEXT NOT NULL,
              movement_type TEXT NOT NULL,quantity_delta INTEGER NOT NULL,reason TEXT NOT NULL,
              reference_id TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS oc_purchase_orders(
              id TEXT PRIMARY KEY,business_id TEXT NOT NULL,supplier_id TEXT NOT NULL,
              status TEXT NOT NULL,currency TEXT NOT NULL,notes TEXT NOT NULL,
              created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS oc_purchase_order_lines(
              id TEXT PRIMARY KEY,po_id TEXT NOT NULL,business_id TEXT NOT NULL,
              product_id TEXT NOT NULL,sku_snapshot TEXT NOT NULL,name_snapshot TEXT NOT NULL,
              quantity_ordered INTEGER NOT NULL,unit_cost_minor INTEGER NOT NULL,
              quantity_received INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS oc_purchase_receipts(
              id TEXT PRIMARY KEY,po_id TEXT NOT NULL,business_id TEXT NOT NULL,
              product_id TEXT NOT NULL,quantity_received INTEGER NOT NULL,
              evidence_reference TEXT NOT NULL,created_at TEXT NOT NULL,
              UNIQUE(id,po_id,product_id));
            """)
            db.commit()

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def _product(self,business_id,product_id):
        row=self._db.execute("SELECT id,sku,name,currency,status FROM opencompany_products WHERE business_id=? AND id=?",
                             (business_id,str(product_id))).fetchone()
        if not row: raise ValueError("Product not found in this business unit.")
        return dict(row)

    def get_balance(self,business_id,product_id):
        with self._lock:
            self._product(business_id,product_id)
            row=self._db.execute("SELECT * FROM oc_inventory_balance WHERE business_id=? AND product_id=?",
                                  (business_id,str(product_id))).fetchone()
        return dict(row) if row else {"business_id":business_id,"product_id":str(product_id),
            "quantity_on_hand":0,"low_stock_threshold":0,"updated_at":None}

    def list_balances(self,business_id):
        with self._lock:
            rows=self._db.execute("""SELECT b.* FROM oc_inventory_balance b
              JOIN opencompany_products p ON p.id=b.product_id AND p.business_id=b.business_id
              WHERE b.business_id=? ORDER BY p.name""",(business_id,)).fetchall()
        return [dict(row) for row in rows]

    def set_threshold(self,business_id,product_id,threshold):
        if int(threshold)<0: raise ValueError("Threshold cannot be negative.")
        now=self._now()
        with self._lock:
            self._product(business_id,product_id)
            self._db.execute("""INSERT INTO oc_inventory_balance VALUES(?,?,0,?,?)
              ON CONFLICT(business_id,product_id) DO UPDATE SET
              low_stock_threshold=excluded.low_stock_threshold,updated_at=excluded.updated_at""",
              (business_id,str(product_id),int(threshold),now))
            self._db.commit()
        return self.get_balance(business_id,product_id)

    def adjust_stock(self,business_id,product_id,delta,reason,owner_confirmed=False):
        delta=int(delta);reason=str(reason).strip()
        if not owner_confirmed: raise PermissionError("Owner confirmation is required.")
        if not reason: raise ValueError("A reason is required for stock adjustment.")
        if delta==0: raise ValueError("Stock adjustment must be nonzero.")
        now=self._now();movement_id=str(uuid4())
        with self._lock:
            self._product(business_id,product_id)
            row=self._db.execute("SELECT quantity_on_hand,low_stock_threshold FROM oc_inventory_balance WHERE business_id=? AND product_id=?",
                                 (business_id,str(product_id))).fetchone()
            old=int(row["quantity_on_hand"]) if row else 0
            threshold=int(row["low_stock_threshold"]) if row else 0
            if old+delta<0: raise ValueError("Adjustment cannot make stock negative.")
            self._db.execute("""INSERT INTO oc_inventory_balance VALUES(?,?,?, ?,?)
              ON CONFLICT(business_id,product_id) DO UPDATE SET quantity_on_hand=excluded.quantity_on_hand,updated_at=excluded.updated_at""",
              (business_id,str(product_id),old+delta,threshold,now))
            self._db.execute("INSERT INTO oc_inventory_movement VALUES(?,?,?,?,?,?,?,?)",
              (movement_id,business_id,str(product_id),"owner_adjustment",delta,reason[:1200],"",now))
            self._db.commit()
        return self.get_balance(business_id,product_id)

    def movements(self,business_id,product_id=None):
        with self._lock:
            if product_id:
                self._product(business_id,product_id)
                rows=self._db.execute("SELECT * FROM oc_inventory_movement WHERE business_id=? AND product_id=? ORDER BY created_at",
                  (business_id,str(product_id))).fetchall()
            else:
                rows=self._db.execute("SELECT * FROM oc_inventory_movement WHERE business_id=? ORDER BY created_at",
                  (business_id,)).fetchall()
        return [dict(row) for row in rows]

    def create_purchase_order(self,business_id,supplier_id,items,currency,notes="",owner_confirmed=False):
        if not owner_confirmed: raise PermissionError("Owner confirmation is required to create a purchase order.")
        currency=str(currency).upper()
        if len(currency)!=3 or not currency.isalpha(): raise ValueError("A 3-letter currency code is required.")
        if not items: raise ValueError("A purchase order must contain items.")
        now=self._now();po_id=str(uuid4());normalized=[]
        with self._lock:
            supplier=self._db.execute("SELECT id FROM opencompany_counterparties WHERE business_id=? AND id=? AND kind='supplier' AND status='active'",
              (business_id,str(supplier_id))).fetchone()
            if not supplier: raise ValueError("Active supplier not found in this business unit.")
            for item in items:
                p=self._product(business_id,item["product_id"])
                qty=int(item["quantity"]);cost=int(item["unit_cost_minor"])
                if qty<1 or qty>100000 or cost<0: raise ValueError("Invalid PO quantity or unit cost.")
                if p["currency"]!=currency: raise ValueError("Product currency must match purchase order currency.")
                normalized.append({"id":str(uuid4()),"product_id":p["id"],"sku_snapshot":p["sku"],
                  "name_snapshot":p["name"],"quantity_ordered":qty,"unit_cost_minor":cost})
            self._db.execute("INSERT INTO oc_purchase_orders VALUES(?,?,?,?,?,?,?,?)",
              (po_id,business_id,str(supplier_id),"draft",currency,str(notes)[:1200],now,now))
            for line in normalized:
                self._db.execute("INSERT INTO oc_purchase_order_lines VALUES(?,?,?,?,?,?,?,?,0)",
                  (line["id"],po_id,business_id,line["product_id"],line["sku_snapshot"],line["name_snapshot"],line["quantity_ordered"],line["unit_cost_minor"]))
            self._db.commit()
        return self.get_purchase_order(business_id,po_id)

    def get_purchase_order(self,business_id,po_id):
        with self._lock:
            row=self._db.execute("SELECT * FROM oc_purchase_orders WHERE business_id=? AND id=?",
              (business_id,str(po_id))).fetchone()
            if not row:return None
            lines=self._db.execute("SELECT * FROM oc_purchase_order_lines WHERE business_id=? AND po_id=? ORDER BY rowid",
              (business_id,str(po_id))).fetchall()
        result=dict(row);result["lines"]=[dict(x) for x in lines]
        result["total_minor"]=sum(int(x["quantity_ordered"])*int(x["unit_cost_minor"]) for x in lines)
        result["received_total_minor"]=sum(int(x["quantity_received"])*int(x["unit_cost_minor"]) for x in lines)
        return result

    def list_purchase_orders(self,business_id):
        with self._lock:
            rows=self._db.execute("SELECT id FROM oc_purchase_orders WHERE business_id=? ORDER BY created_at DESC",
              (business_id,)).fetchall()
        return [self.get_purchase_order(business_id,r["id"]) for r in rows]

    def receive(self,business_id,po_id,product_id,quantity,evidence_reference,owner_confirmed=False):
        if not owner_confirmed: raise PermissionError("Owner confirmation is required to record receipt.")
        quantity=int(quantity);evidence=str(evidence_reference).strip()
        if quantity<1: raise ValueError("Receipt quantity must be positive.")
        if not evidence: raise ValueError("Receipt evidence reference is required.")
        now=self._now();receipt_id=str(uuid4())
        with self._lock:
            po=self._db.execute("SELECT status,currency FROM oc_purchase_orders WHERE business_id=? AND id=?",
              (business_id,str(po_id))).fetchone()
            if not po or po["status"] not in ("draft","open","partially_received"): raise ValueError("Purchase order is not receivable.")
            line=self._db.execute("SELECT * FROM oc_purchase_order_lines WHERE business_id=? AND po_id=? AND product_id=?",
              (business_id,str(po_id),str(product_id))).fetchone()
            if not line: raise ValueError("Product is not part of this purchase order.")
            remaining=int(line["quantity_ordered"])-int(line["quantity_received"])
            if quantity>remaining: raise ValueError("Receipt exceeds the outstanding ordered quantity.")
            self._db.execute("INSERT INTO oc_purchase_receipts VALUES(?,?,?,?,?,?,?)",
              (receipt_id,str(po_id),business_id,str(product_id),quantity,evidence[:500],now))
            self._db.execute("UPDATE oc_purchase_order_lines SET quantity_received=quantity_received+? WHERE id=?",
              (quantity,line["id"]))
            bal=self._db.execute("SELECT quantity_on_hand,low_stock_threshold FROM oc_inventory_balance WHERE business_id=? AND product_id=?",
              (business_id,str(product_id))).fetchone()
            old=int(bal["quantity_on_hand"]) if bal else 0;threshold=int(bal["low_stock_threshold"]) if bal else 0
            self._db.execute("""INSERT INTO oc_inventory_balance VALUES(?,?,?, ?,?)
              ON CONFLICT(business_id,product_id) DO UPDATE SET quantity_on_hand=excluded.quantity_on_hand,updated_at=excluded.updated_at""",
              (business_id,str(product_id),old+quantity,threshold,now))
            self._db.execute("INSERT INTO oc_inventory_movement VALUES(?,?,?,?,?,?,?,?)",
              (str(uuid4()),business_id,str(product_id),"purchase_receipt",quantity,"Owner-attested goods receipt",str(po_id),now))
            remaining_after=int(line["quantity_ordered"])-int(line["quantity_received"])-quantity
            newstatus="received" if remaining_after==0 else "partially_received"
            all_lines=self._db.execute("SELECT quantity_ordered,quantity_received FROM oc_purchase_order_lines WHERE po_id=?",
              (str(po_id),)).fetchall()
            if all(int(x["quantity_ordered"])==int(x["quantity_received"])+(quantity if x is line else 0) for x in all_lines):
                newstatus="received"
            self._db.execute("UPDATE oc_purchase_orders SET status=?,updated_at=? WHERE id=?",
              (newstatus,now,str(po_id)))
            self._db.commit()
        return {"receipt_id":receipt_id,"purchase_order":self.get_purchase_order(business_id,po_id),
          "stock_balance":self.get_balance(business_id,product_id),"external_purchase_made":False}
