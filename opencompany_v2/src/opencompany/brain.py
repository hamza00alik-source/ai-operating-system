"""Local persistent memory; retrieval is deterministic and transparent in v0.1."""
import sqlite3,re
from datetime import datetime,timezone
class Brain:
 def __init__(self,connection):self.db=connection
 def initialize(self):
  self.db.execute("""CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,scope TEXT NOT NULL,topic TEXT NOT NULL,content TEXT NOT NULL,source TEXT NOT NULL,confidence REAL NOT NULL,approval TEXT NOT NULL,created_at TEXT NOT NULL)""");self.db.commit()
 def propose(self,scope,topic,content,source,confidence=.4):
  if not 0<=confidence<=1:raise ValueError("confidence must be 0..1")
  import uuid
  now=datetime.now(timezone.utc).isoformat()
  self.db.execute("INSERT INTO memories VALUES(?,?,?,?,?,?,?,?)",(str(uuid.uuid4()),scope,topic,content,source,confidence,"proposed",now));self.db.commit()
 def review(self,memory_id,approve:bool):
  status="approved" if approve else "rejected"
  cur=self.db.execute("UPDATE memories SET approval=? WHERE id=? AND approval='proposed'",(status,memory_id));self.db.commit();return cur.rowcount==1
 def recall(self,query,scope="company",limit=5):
  words=set(re.findall(r"[a-z0-9]{3,}",query.lower()))
  rows=self.db.execute("SELECT * FROM memories WHERE approval='approved' AND scope IN (?, 'company') ORDER BY created_at DESC LIMIT 500",(scope,)).fetchall()
  ranked=[]
  for r in rows:
   text=(r["topic"]+" "+r["content"]).lower();overlap=len(words & set(re.findall(r"[a-z0-9]{3,}",text)))
   if overlap:ranked.append((overlap/max(1,len(words)),r["confidence"],r))
  ranked.sort(key=lambda x:(x[0],x[1]),reverse=True)
  return [dict(row) for _,_,row in ranked[:max(1,min(limit,20))]]
