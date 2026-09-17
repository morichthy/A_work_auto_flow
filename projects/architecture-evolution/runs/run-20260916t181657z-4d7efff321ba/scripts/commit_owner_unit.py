"""Commit only the reviewed L1 update; later closure stages depend on it."""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import sys, uuid
ROOT=Path(__file__).resolve().parents[5]; RUN=Path(__file__).resolve().parents[1]
OUT=RUN/".run-captures"/"memory-closure"; OWNER="PRJ-ARCHITECTURE-EVOLUTION"; ID="MEM-1b419e02-3f69-5690-a1d5-1d5f0bdd588b"; HEAD="COM-d6b78fdc-f63e-4517-96e5-9f73dbe3a888"
def put(n,x):
 OUT.mkdir(parents=True,exist_ok=True); p=OUT/n; s=json.dumps(x,ensure_ascii=False,indent=2)+"\n"; 
 if p.exists() and p.read_text(encoding="utf-8")!=s: raise RuntimeError(f"receipt differs: {p}")
 if not p.exists(): p.write_text(s,encoding="utf-8")
def main():
 sys.path.insert(0,str(ROOT/"automation"/"scripts")); from memory import api,contracts; from memory.service import MemoryService; from evidence import fingerprint
 old=json.loads((RUN/".run-captures"/"consolidation-baseline"/"reader-unit.json").read_text(encoding="utf-8"))["record"]
 src=Path(__file__).with_name("apply_owner_document_results.py").read_text(encoding="utf-8"); result=src.split('RESULT = """',1)[1].split('"""',1)[0]
 d={k:deepcopy(old[k]) for k in (*contracts.CONTENT_FIELDS,"schema_version","record_reason")}; run=json.loads((RUN/"run.json").read_text(encoding="utf-8-sig")); rr={"target_kind":"owner","target_id":run["run_id"],"revision":None,"sha256":fingerprint(run),"relation":"input","locator":"RESULTS与已登记固定Run产物"}
 d["change_reason"]="追加Owner文稿渐进阅读、note预算及冻结Run验证边界。"; d["keywords"]=list(dict.fromkeys(d["keywords"]+["owner_document","max_owners","note_max_tokens"])); d["sources"].append(rr); d["payload"]["evidence_refs"].append(rr); d["payload"]["blocks"].append({"block_id":"owner-document-results","role":"results","markdown":result,"requires_block_ids":[]})
 q={"schema_version":3,"request_id":str(uuid.uuid4()),"actor":{"kind":"ai","id":"codex-owner-document-closure"},"owner_id":OWNER,"expected_head":HEAD,"operations":[{"op":"put_record","record_id":ID,"expected_revision":old["revision"],"draft":d}]}
 put("01-unit-request.json",q); svc=MemoryService(ROOT)
 for action,name in [("validate-draft","01-unit-preflight.json"),("commit","01-unit-commit.json")]:
  r=api.dispatch(svc,action,q); put(name,r)
  if r.get("error") or (action=="validate-draft" and not r.get("valid")): raise RuntimeError(r)
 r=api.dispatch(svc,"inspect",{"owner_id":OWNER,"record_id":ID,"revision":old["revision"]+1}); put("01-unit-readback.json",r)
 if r.get("error"): raise RuntimeError(r)
 print(json.dumps({"commit_id":api.dispatch(svc,"inspect",{"owner_id":OWNER})["head"]["commit_id"],"record":r["record"]},ensure_ascii=False))
if __name__=="__main__": main()
