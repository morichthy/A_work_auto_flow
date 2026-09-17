"""CAS-save the frozen Owner-document reading results through public memory APIs."""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[5]
RUN = Path(__file__).resolve().parents[1]
OUT = RUN / ".run-captures" / "memory-closure"
OWNER = "PRJ-ARCHITECTURE-EVOLUTION"
IDS = {"unit":"MEM-1b419e02-3f69-5690-a1d5-1d5f0bdd588b", "section":"MEM-50f66b7c-7953-5715-8b70-5ae7705176ab", "overview":"MEM-b8db41b4-3a97-5f26-ba21-87f6cce7d155", "document":"MEM-bd121869-a0b9-59e3-af23-8e8675374a63"}
EXPECTED = "COM-d6b78fdc-f63e-4517-96e5-9f73dbe3a888"

RESULT = """# Owner文稿阅读与note上下文预算

Run：RUN-20260916T181657Z-4D7EFFF321BA。候选收敛为正文 text 与真实 owner_id，跨路线按固定正文身份去重；每个 Owner、每页先交付一段，read 确认后跳过其余 pending 段。随后逐 Owner 读取一篇最新完整 research_process；图片、L0 与 Run 仅保留固定引用并按需展开，主 Agent 只接收研究式 note。

新 owner_document 模式的内部搜索与排名诊断不计 AI 输出；每个 operation 的 engineering Ledger 仍保护资源。旧 RS 或缺 mode 的旧 start 保持 legacy 累计预算语义。设置 `max_owners=10`、`note_max_tokens=6000`；估算是 UTF-8 字节的保守代理，不等同宿主实际 token。

后端84个不同用例（其中Owner模式19）、设置Python18、组件11、浏览器2及扩展旧工作区setup19均有通过记录；类型检查、生产构建、refresh-index和validate通过（validate为0错误、21既有警告）。这些是分阶段结果，不是一次全套84连跑。

最终normal RS为RS-a8f812d7-d8f9-4862-8e8f-932cc5649d3 r8：handoff纳入1份note、0遗漏，估算5517/6000，note本体4736；主Agent实际回读。note保留Kahan递推、三轮计数/误差与失败输入、三Run及四图固定引用；图/L0/Run未独立展开或复算，pairwise无算法/实验依据。完整性仍为false，唯一程序缺口为Cross Encoder长正文窗口回退。

最终渐进场景首批为1 Owner/1段/320正文字符，`result_limit=10`及重排池30未降低；外层recall墙钟88.743秒。不同查询、中间实现及同时运行的合成测试使其不能作为前后加速比较；未测宿主AI内部时间或费用，Recall/nDCG、总体时延、独立质量题集、第二物理机、真实业务/人工验收与发布仍待完成。"""

def put(name, obj):
    OUT.mkdir(parents=True, exist_ok=True); p=OUT/name; s=json.dumps(obj,ensure_ascii=False,indent=2)+"\n"
    if p.exists() and p.read_text(encoding="utf-8")!=s: raise RuntimeError(f"receipt differs: {p}")
    if not p.exists(): p.write_text(s,encoding="utf-8")
def ref(r): return {"target_kind":"record","target_id":r["record_id"],"revision":r["revision"],"sha256":r["record_hash"],"relation":"references","locator":""}
def uniq(xs):
    out=[]
    for x in xs:
        if x not in out: out.append(x)
    return out
def main():
    sys.path.insert(0,str(ROOT/"automation"/"scripts")); from memory import api,contracts; from memory.service import MemoryService; from evidence import fingerprint
    svc=MemoryService(ROOT)
    def call(a,q):
        r=api.dispatch(svc,a,q)
        if r.get("error"): raise RuntimeError(r["error"])
        return r
    start=call("inspect",{"owner_id":OWNER}); put("head-before.json",start)
    if start["head"]["commit_id"]!=EXPECTED: raise RuntimeError("Owner HEAD changed after reviewed baseline")
    old={k:call("inspect",{"owner_id":OWNER,"record_id":v})["record"] for k,v in IDS.items()}
    run=json.loads((RUN/"run.json").read_text(encoding="utf-8-sig")); rr={"target_kind":"owner","target_id":run["run_id"],"revision":None,"sha256":fingerprint(run),"relation":"input","locator":"RESULTS与已登记固定Run产物"}
    def draft(r): return {k:deepcopy(r[k]) for k in (*contracts.CONTENT_FIELDS,"schema_version","record_reason")}
    def save(label, changes, head):
        ops=[]
        for k,d in changes.items(): ops.append({"op":"put_record","record_id":IDS[k],"expected_revision":old[k]["revision"],"draft":d})
        q={"schema_version":3,"request_id":str(uuid.uuid4()),"actor":{"kind":"ai","id":"codex-owner-document-closure"},"owner_id":OWNER,"expected_head":head,"operations":ops}
        put(label+"-request.json",q); v=call("validate-draft",q); put(label+"-preflight.json",v)
        if not v.get("valid"): raise RuntimeError(v)
        c=call("commit",q); put(label+"-commit.json",c); got={}
        for k in changes:
            got[k]=call("inspect",{"owner_id":OWNER,"record_id":IDS[k],"revision":old[k]["revision"]+1})["record"]; put(label+"-"+k+"-readback.json",got[k])
        return got,c["commit_id"]
    u=draft(old["unit"]); u["change_reason"]="追加Owner文稿渐进阅读、note预算及冻结Run验证边界。"; u["keywords"]=uniq(u["keywords"]+["owner_document","max_owners","note_max_tokens"]); u["sources"]=uniq(u["sources"]+[rr]); u["payload"]["evidence_refs"]=uniq(u["payload"]["evidence_refs"]+[rr]); u["payload"]["blocks"].append({"block_id":"owner-document-results","role":"results","markdown":RESULT,"requires_block_ids":[]})
    one,h=save("01-unit",{"unit":u},start["head"]["commit_id"]); ur=ref(one["unit"])
    s=draft(old["section"]); s["change_reason"]="追加Owner文稿阅读模式与冻结Run验证结果。"
    for b in s["payload"]["blocks"]:
        if b.get("type")=="unit" and b.get("ref",{}).get("target_id")==IDS["unit"]: b["ref"]=ur; b["block_ids"]=uniq(b.get("block_ids",[])+["owner-document-results"])
    s["payload"]["blocks"].insert(0,{"type":"prose","markdown":"本轮新增Owner文稿渐进阅读与note预算模式；历史委派、计时、预算失败块均保留其原有范围。\n\n"+RESULT.split("\n\n",1)[1],"evidence_refs":[ur]}); s["sources"]=uniq([x for x in s["sources"] if x["target_id"]!=IDS["unit"]]+[ur])
    o=draft(old["overview"]); o["change_reason"]="追加Owner文稿阅读与note预算冻结结果。"; o["body_markdown"]+="\n\n## Owner文稿阅读补充\n\n"+RESULT; o["payload"]["results"].append("Owner文稿渐进阅读、完整research_process读取与最终r8 note已按固定Run验证；CE长正文窗口回退保留。"); o["payload"]["limitations"]=uniq(o["payload"]["limitations"]+["新模式使用per-operation engineering Ledger；内部搜索/诊断不占AI输出，旧legacy累计预算语义不变。", "最终note完整性仍因CE回退为false；不宣称性能、总费用或业务正确率改善。"]); o["payload"]["technical_refs"]=uniq(o["payload"]["technical_refs"]+[ur]); o["sources"]=uniq(o["sources"]+[ur])
    two,h=save("02-section-overview",{"section":s,"overview":o},h); sr=ref(two["section"])
    d=draft(old["document"]); d["change_reason"]="追加Owner文稿阅读及note预算冻结结果，保留现有两章节。"; d["payload"]["section_refs"]=[sr if x["target_id"]==IDS["section"] else x for x in d["payload"]["section_refs"]]; d["payload"]["common_refs"]=uniq([x for x in d["payload"]["common_refs"] if x["target_id"]!=IDS["unit"]]+[ur]); d["payload"]["scope"]+="；追加Owner文稿渐进阅读与note预算冻结结果，保留CE回退及性能边界。"; d["sources"]=uniq(d["payload"]["common_refs"]+d["payload"]["section_refs"])
    three,h=save("03-document",{"document":d},h); q={"owner_id":OWNER,"document_id":IDS["document"],"revision":three["document"]["revision"]}; report=call("document",q); impact=call("document-impact",q); put("final-document.json",report); put("final-impact.json",impact)
    if not report["report"]["complete"]: raise RuntimeError("document assembly incomplete")
    end=call("inspect",{"owner_id":OWNER}); put("head-after.json",end); put("identities.json",{k:ref(v) for k,v in {**one,**two,**three}.items()}); print(json.dumps({"head":end["head"],"records":{k:ref(v) for k,v in {**one,**two,**three}.items()}},ensure_ascii=False))
if __name__=="__main__": main()
