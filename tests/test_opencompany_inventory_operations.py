import sqlite3
from threading import RLock
from uuid import uuid4
import pytest
from opencompany_core.business_operations import BusinessOperationsRepository
from opencompany_core.inventory_operations import InventoryOperationsRepository

@pytest.fixture
def repos():
    db=sqlite3.connect(":memory:",check_same_thread=False)
    db.row_factory=sqlite3.Row
    lock=RLock()
    business=BusinessOperationsRepository(db,lock)
    inventory=InventoryOperationsRepository(db,lock)
    return db,business,inventory

def seed(business,business_id="physical-brand"):
    supplier={"id":"sup-"+business_id,"business_id":business_id,"kind":"supplier","name":"Supplier",
        "country":"PK","reference":"","status":"active","created_at":"2026-01-01T00:00:00Z"}
    product={"id":"prod-"+business_id,"business_id":business_id,"sku":"SKU-"+business_id,
        "name":"Test Product","description":"","unit_price_minor":1500,"currency":"USD",
        "supplier_id":supplier["id"],"status":"active","created_at":"2026-01-01T00:00:00Z",
        "updated_at":"2026-01-01T00:00:00Z"}
    business.create_counterparty(supplier);business.create_product(product)
    return supplier,product

def test_adjustment_requires_owner_and_reason_and_blocks_negative(repos):
    _,business,inv=repos
    supplier,product=seed(business)
    with pytest.raises(PermissionError):inv.adjust_stock(product["business_id"],product["id"],2,"initial",False)
    with pytest.raises(ValueError):inv.adjust_stock(product["business_id"],product["id"],2,"",True)
    inv.adjust_stock(product["business_id"],product["id"],5,"opening count",True)
    with pytest.raises(ValueError):inv.adjust_stock(product["business_id"],product["id"],-6,"mistake",True)
    assert inv.get_balance(product["business_id"],product["id"])["quantity_on_hand"]==5
    assert len(inv.movements(product["business_id"],product["id"]))==1

def test_purchase_receipt_idempotency_and_stock_increase(repos):
    _,business,inv=repos
    supplier,product=seed(business)
    po=inv.create_purchase_order(product["business_id"],supplier["id"],[
        {"product_id":product["id"],"quantity":4,"unit_cost_minor":500}
    ],"USD",owner_confirmed=True)
    receipt=inv.receive(product["business_id"],po["id"],product["id"],2,"packing-slip-1",True)
    balance=receipt["stock_balance"]["quantity_on_hand"]
    replay=inv.receive(product["business_id"],po["id"],product["id"],2,"packing-slip-1",True)
    assert replay["idempotent_replay"] is True
    assert replay["stock_balance"]["quantity_on_hand"]==balance==2
    assert inv.get_purchase_order(product["business_id"],po["id"])["status"]=="partially_received"

def test_business_unit_isolation(repos):
    _,business,inv=repos
    supplier,product=seed(business,"physical-brand")
    supplier2,product2=seed(business,"physical-agency")
    with pytest.raises(ValueError):
        inv.create_purchase_order("physical-agency",supplier["id"],[
            {"product_id":product["id"],"quantity":1,"unit_cost_minor":100}
        ],"USD",owner_confirmed=True)
    with pytest.raises(ValueError):
        inv.get_balance("physical-agency",product["id"])
    inv.adjust_stock("physical-brand",product["id"],3,"count",True)
    assert inv.get_balance("physical-agency",product2["id"])["quantity_on_hand"]==0
