import sqlite3
from opencompany.agent import AgentProfile,AgentResult
from opencompany.brain import Brain
from opencompany.ceo import CEOPlanner

def test_agent_contract_and_budget():
 a=AgentProfile("researcher","Find evidence",("research",),max_steps=4).validate()
 assert a.can("research") and not a.can("publish")
 assert AgentResult("completed","done",steps_used=4).validate(a.max_steps)
def test_brain_only_recalls_approved():
 db=sqlite3.connect(":memory:");db.row_factory=sqlite3.Row;b=Brain(db);b.initialize()
 b.propose("company","pricing","Pricing test results","run-1",.7)
 mem=db.execute("SELECT id FROM memories").fetchone()["id"]
 assert b.recall("pricing test")==[]
 assert b.review(mem,True)
 assert len(b.recall("pricing test"))==1
def test_ceo_plan_bounds():
 p=CEOPlanner().draft_plan("launch experiment",[{"title":"Research","objective":"Collect evidence"}])
 assert p.validate().goal
