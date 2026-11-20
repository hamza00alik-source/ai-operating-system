"""Treasury offline primitives tests."""
import sqlite3
import threading
import pytest
from opencompany_core.treasury import TreasuryRepository

@pytest.fixture
def treasury():
    db=sqlite3.connect(":memory:",check_same_thread=False)
    db.row_factory=sqlite3.Row
    repo=TreasuryRepository(db,threading.RLock())
    yield repo
    db.close()

def test_account_is_business_scoped(treasury):
    account=treasury.create_account("digital-products","Operating cash","USD",masked_reference="***1234")
    assert treasury.list_accounts("digital-products")[0]["masked_reference"]=="***1234"
    assert treasury.list_accounts("physical-brand")==[]
    assert account["status"]=="record_only"

def test_spend_request_requires_positive_amount_and_self_approval_is_blocked(treasury):
    req=treasury.submit_spend_request("digital-products","agent-1","Vendor","Hosting",1500,"USD")
    assert req["status"]=="pending_approval"
    with pytest.raises(ValueError,match="positive"):
        treasury.submit_spend_request("digital-products","agent-1","Vendor","Hosting",0,"USD")
    with pytest.raises(ValueError,match="own"):
        treasury.decide_spend_request("digital-products",req["id"],"agent-1",True)
    approved=treasury.decide_spend_request("digital-products",req["id"],"owner",True,"Reviewed")
    assert approved["status"]=="approved"
    assert treasury.list_spend_requests("physical-agency")==[]

def test_reject_request_and_no_redecision(treasury):
    req=treasury.submit_spend_request("physical-agency","agent","Payee","Reason",100,"PKR")
    rejected=treasury.decide_spend_request("physical-agency",req["id"],"owner",False,"Not allowed")
    assert rejected["status"]=="rejected"
    with pytest.raises(ValueError,match="pending"):
        treasury.decide_spend_request("physical-agency",req["id"],"owner",True)

def test_journal_requires_balanced_same_business_currency_entries(treasury):
    cash=treasury.create_account("physical-brand","Cash","PKR","cash")
    revenue=treasury.create_account("physical-brand","Revenue","PKR","revenue")
    posted=treasury.post_journal("physical-brand","PKR","revenue","sale-1","Sale recorded",[
        {"account_id":cash["id"],"debit_minor":10000,"credit_minor":0},
        {"account_id":revenue["id"],"debit_minor":0,"credit_minor":10000},
    ])
    assert posted["total_debits_minor"]==posted["total_credits_minor"]==10000
    assert posted["funds_moved"] is False
    with pytest.raises(ValueError,match="balance"):
        treasury.post_journal("physical-brand","PKR","bad","x","unbalanced",[
            {"account_id":cash["id"],"debit_minor":10,"credit_minor":0},
            {"account_id":revenue["id"],"debit_minor":0,"credit_minor":5},
        ])
    other=treasury.create_account("digital-products","Cash","PKR")
    with pytest.raises(ValueError,match="business"):
        treasury.post_journal("physical-brand","PKR","cross","x","scope",[ 
            {"account_id":cash["id"],"debit_minor":1,"credit_minor":0},
            {"account_id":other["id"],"debit_minor":0,"credit_minor":1},
        ])
