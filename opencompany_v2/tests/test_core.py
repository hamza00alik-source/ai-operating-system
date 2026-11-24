from opencompany.domain import Opportunity, Task, CompanyEvent
from opencompany.scoring import score_opportunity
from opencompany.store import Store

def test_scoring_weights():
    item=Opportunity("sample","",80,80,80,80,80,80)
    assert score_opportunity(item).total == 80

def test_score_rejects_invalid_input():
    item=Opportunity("bad","",120,50,50,50,50,50)
    try: score_opportunity(item)
    except ValueError: pass
    else: assert False, "invalid score accepted"

def test_event_chain_integrity(tmp_path):
    store=Store(str(tmp_path/"test.db"))
    store.append_event(CompanyEvent("created","owner","task","1",{}))
    store.append_event(CompanyEvent("updated","agent","task","1",{"status":"ready"}))
    assert store.verify_event_chain()
    store.close()
