"""F1 的最小合法材料查询 fixture，仅用于隔离的软件测试。

用法::

    with tempfile.TemporaryDirectory() as boundary:
        fx = materialize(Path(boundary) / "F1 中文 workspace", isolation_root=boundary)
        old = fx.inspect("A.unit.r1")
        fixed = fx.ref("A.unit.r1")  # 旧版 record_hash，不跟随当前 HEAD。

Owner/原件/来源登记是显式合成 bootstrap；Run 通过现有创建与登记函数建立。
所有规范记录、修订、review 和 association 均通过 memory.api.dispatch 写入。
本文件不读写旧冻结 fixture，不伪造 HEAD、服务字段或科学验证结果。
返回的标签只是测试配方预期，不是实际 AI 语义判断或新查询接口的执行回执。
"""
from __future__ import annotations

from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import uuid
from unittest.mock import patch


REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPTS = REPOSITORY / "automation" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import evidence
import run_capture
import workspace_cli
from memory import api, contracts
from memory.service import MemoryService


FIXTURE_VERSION = "F1-minimal-v1"
NAMESPACE = uuid.UUID("d13bb01e-ae14-4e68-a3e4-d7694a7d2789")
ACTOR = {"kind": "workflow", "id": "SYNTHETIC-ONLY-material-query-fixture"}
SCOPE = "synthetic:material-query-only"
HIDDEN_TITLE = "MQ_HIDDEN_OWNER_TITLE_禁止泄露"
HIDDEN_BODY = "MQ_HIDDEN_ORIGINAL_BODY_禁止泄露"


def _uuid(label):
    """以配方标签产生 UUID；稳定身份不能依赖临时目录名或机器时间。"""
    return str(uuid.uuid5(NAMESPACE, label))


def _write_json(path, value):
    """只写本函数创建的隔离副本；规范记忆文件绝不经过此函数。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FixtureClock:
    """服务可注入的固定 UTC 时钟，advance 的单位为秒。"""

    def __init__(self):
        self.value = datetime(2026, 9, 1, tzinfo=timezone.utc)

    def __call__(self):
        return self.value.isoformat(timespec="seconds").replace("+00:00", "Z")

    def advance(self, seconds=1):
        if type(seconds) is not int or seconds < 0:
            raise ValueError("合成时钟只能按非负整数秒前进")
        self.value += timedelta(seconds=seconds)


class _CommitIds:
    """仅注入已有 store 构造参数，不绕过实际提交或自己生成 MEM 记录。"""

    def __init__(self):
        self.position = 0

    def __call__(self):
        self.position += 1
        return _uuid("commit:" + str(self.position))


@dataclass
class MaterialQueryFixture:
    root: Path
    service: MemoryService
    clock: FixtureClock
    owner_ids: dict
    sources: dict
    run_ids: dict
    records: dict = field(default_factory=dict)
    record_ids: dict = field(default_factory=dict)
    refs: dict = field(default_factory=dict)
    receipts: list = field(default_factory=list)
    claims: dict = field(default_factory=dict)
    labels: dict = field(default_factory=dict)
    invalid_drafts: dict = field(default_factory=dict)
    limits: list = field(default_factory=list)

    def ref(self, key, relation="references"):
        """返回副本，防止调用者改一条引用时污染其他测试的固定依据。"""
        return {**deepcopy(self.refs[key]), "relation": relation}

    def source_ref(self, alias, relation="input"):
        source = self.sources[alias]
        return {"target_kind": "file", "target_id": source["source_id"], "revision": None,
                "sha256": source["sha256"], "locator": "完整合成输入", "relation": relation}

    def inspect(self, key):
        record = self.records[key]
        return api.dispatch(self.service, "inspect", {
            "owner_id": record["owner_id"], "record_id": record["record_id"],
            "revision": record["revision"]})["record"]

    def head(self, alias):
        value = api.dispatch(self.service, "inspect", {"owner_id": self.owner_ids.get(alias, alias)})
        return (value["head"] or {}).get("commit_id")

    def _remember(self, key, record):
        self.records[key] = deepcopy(record)
        self.record_ids[key] = record["record_id"]
        self.refs[key] = {"target_kind": "record", "target_id": record["record_id"],
                          "revision": record["revision"], "sha256": record["record_hash"],
                          "locator": "", "relation": "references"}
        return record

    def commit_draft(self, key, draft, previous=None):
        """经公开校验和提交写入；previous 为配方键或先前真实回读记录。"""
        self.clock.advance()
        old = self.records[previous] if isinstance(previous, str) else previous
        operation = {"op": "put_record", "draft": deepcopy(draft)}
        if old is None:
            operation["client_key"] = key
        else:
            operation.update(record_id=old["record_id"], expected_revision=old["revision"])
        request = {"schema_version": 1, "request_id": _uuid("put:" + key), "actor": ACTOR,
                   "owner_id": draft["owner_id"], "expected_head": self.head(draft["owner_id"]),
                   "operations": [operation]}
        api.dispatch(self.service, "validate-draft", request)
        receipt = api.dispatch(self.service, "commit", request)
        if receipt["save_status"] != "committed":
            raise AssertionError("配方创建必须产生真实提交：" + repr(receipt))
        self.receipts.append({"key": key, "action": "commit", "request": request, "receipt": receipt})
        result = receipt["record_results"][0]
        record = api.dispatch(self.service, "inspect", {"owner_id": draft["owner_id"],
                              "record_id": result["record_id"], "revision": result["revision"]})["record"]
        return self._remember(key, record)

    def revise(self, key, previous, **changes):
        old = self.records[previous]
        draft = {name: deepcopy(old[name]) for name in
                 (*contracts.CONTENT_FIELDS, "schema_version", "record_reason")}
        draft.update(changes, change_reason="SYNTHETIC ONLY：配方中的显式新修订")
        return self.commit_draft(key, draft, old)

    def review(self, key, record_key, claim_id, state="accepted", replacement=None):
        """真实调用 review；认可只用于验证软件状态，绝非现实领域验收。"""
        self.clock.advance()
        record = self.records[record_key]
        claim = next(item for item in record["payload"]["claims"] if item["claim_id"] == claim_id)
        request = {"schema_version": 1, "request_id": _uuid("review:" + key), "actor": ACTOR,
                   "owner_id": record["owner_id"], "expected_head": self.head(record["owner_id"]),
                   "target_claim_id": claim_id, "expected_content_hash": record["content_hash"],
                   "state": state, "scope": SCOPE if state == "accepted" else None,
                   "reason": "SYNTHETIC ONLY：验证 review 状态绑定，不代表科学结论复核",
                   "evidence_refs": deepcopy(claim["evidence_refs"]) if state == "accepted" else [],
                   "replacement_claim_id": replacement}
        receipt = api.dispatch(self.service, "review", request)
        self.receipts.append({"key": key, "action": "review", "request": request, "receipt": receipt})
        result = receipt["record_results"][0]
        value = api.dispatch(self.service, "inspect", {"owner_id": record["owner_id"],
                             "record_id": result["record_id"], "revision": result["revision"]})["record"]
        return self._remember(key, value)

    def association(self, key, left, right):
        """沿用 analogous_to 规范关系，由新适配器映射展示名称。"""
        self.clock.advance()
        payload = {"from": self.ref(left), "to": self.ref(right), "relation": "analogous_to",
                   "explanation": "合成导航关系：反馈路径相似，但参数不能直接迁移",
                   "shared_structure": "测量、比较、干预、再测量的闭环",
                   "transfer_limits": ["对象、延迟和执行器不同；须重新验证增益"],
                   "basis_refs": [self.ref(left), self.ref(right)], "status": "accepted"}
        request = {"request_id": _uuid("association:" + key), "actor": ACTOR,
                   "owner_id": self.owner_ids["A"], "expected_head": self.head("A"),
                   "payload": payload, "title": "SYNTHETIC ONLY " + key,
                   "reason": "配方指定已有导航，不授予 scientific accepted",
                   "discovery": "workspace_summary"}
        receipt = api.dispatch(self.service, "associations-decide", request)
        self.receipts.append({"key": key, "action": "associations-decide", "request": request, "receipt": receipt})
        result = receipt["record_results"][0]
        value = api.dispatch(self.service, "inspect", {"owner_id": self.owner_ids["A"],
                             "record_id": result["record_id"], "revision": result["revision"]})["record"]
        return self._remember(key, value)

    @contextmanager
    def source_access(self, alias, *, enabled):
        """仅撤销/恢复临时 sources.json 的条目，退出时恢复原字节。

        故意不重建索引，用于检查“旧索引/固定引用仍在，但读取必须重新鉴权”。
        这是合成授权故障注入，不是产品来源管理接口；不能传任意路径或新 ID。
        """
        if type(enabled) is not bool or alias not in self.sources:
            raise ValueError("需要已知合成来源及布尔 enabled")
        marker = self.root / "SYNTHETIC_ONLY.txt"
        if not marker.is_file() or marker.read_text(encoding="utf-8") != FIXTURE_VERSION + "\n":
            raise ValueError("来源故障只能用于本 fixture 创建的隔离根")
        path = self.root / "retrieval" / "sources.json"
        before = path.read_bytes()
        value = json.loads(before)
        for source in value["sources"]:
            if source["source_id"] == self.sources[alias]["source_id"]:
                source["enabled"] = enabled
        _write_json(path, value)
        try:
            yield
        finally:
            path.write_bytes(before)


def _draft(fx, alias, kind, title, payload, *, sources=None, body=""):
    refs = [fx.source_ref(alias)] if sources is None else deepcopy(sources)
    return {"schema_version": 3, "owner_id": fx.owner_ids[alias], "kind": kind,
            "title": "SYNTHETIC ONLY " + title, "body_markdown": body,
            "keywords": ["合成", "反馈", "增益", title], "payload": deepcopy(payload),
            "sources": refs, "provenance_gap": None if refs else "合成软件配方，无现实依据",
            "record_reason": "F1：验证现有公开 API 的合法材料状态",
            "discovery": "workspace_summary", "sensitivity": "internal"}


def _unit(fx, alias, *, revision=1):
    """定义 d、方法 m、结果 r；m 依赖 d，r 依赖 m，不复制摘要作全文。"""
    return {"unit_type": "method", "run_ref": None, "evidence_refs": [fx.source_ref(alias)],
            "retrieval_description": {
                "question": alias + " 的合成闭环如何限制增益", "method": "先测延迟，再选择增益",
                "key_findings": [f"MQ_{alias}_DIGEST_R{revision}：这是配方说明，并未执行真实实验"],
                "applicable": ["离散反馈、已知时延的合成设置"],
                "not_applicable": ["离线问卷汇总；不能迁移数值增益"], "limitations": ["未验证真实执行器"]},
            "blocks": [
                {"block_id": "d", "role": "definitions", "markdown":
                 f"MQ_{alias}_DEFINITION：$e_k$ 为归一化误差（无量纲），$u_k$ 为控制量（无量纲），$K$ 为无量纲增益。",
                 "requires_block_ids": []},
                {"block_id": "m", "role": "methods", "markdown":
                 f"MQ_{alias}_METHOD_R{revision}：按 $u_{{k+1}}=u_k+K e_k$ 更新；先确认离散时延。",
                 "requires_block_ids": ["d"]},
                {"block_id": "r", "role": "results", "markdown":
                 f"MQ_{alias}_RESULT_R{revision}：合成配方仅声明版本 {revision} 的边界，未知真实有效性。",
                 "requires_block_ids": ["m"]}], "figures": [], "missing_refs": []}


def _claim(fx, alias, claim_id, statement):
    return {"claim_id": claim_id, "statement": "SYNTHETIC ONLY " + statement,
            "kind": "fact", "scope": SCOPE, "evidence_refs": [fx.source_ref(alias, "supports")]}


def _event(fx, alias, claims=(), *, failed=False, unknown=False):
    failure = {"category": "no_improvement", "tested_scope": SCOPE,
               "result": "配方中的失败条件：延迟增大时直接提高增益", "cannot_infer": "不能据此推断现实控制器无效",
               "retry_conditions": ["重新获得时延和执行器约束"]} if failed else None
    return {"occurred_at": fx.clock(), "question_refs": [], "goal_ref": None, "route_ref": None,
            "action": "记录合成配方条件，未运行现实实验",
            "observation": {"value": None, "reason": "unknown", "note": "未取得观察"} if unknown
            else "MQ_SYNTHETIC_FAILURE" if failed else "MQ_SYNTHETIC_SUCCESS",
            "decision": None, "decision_refs": [], "run_refs": [], "failure": failure, "claims": list(claims)}


def _experience(problem, recommendation, *, failed=False):
    return {"problem_structure": problem, "recommendation": recommendation,
            "applicable": ["SYNTHETIC ONLY：存在反馈且已知时延"],
            "prohibited": ["不得直接外推现实数值或将文本相似当科学支持"],
            "failure_modes": ["延迟未建模引起振荡"] if failed else [],
            "retry_conditions": ["独立检查机制、时延与边界"], "claim_refs": [], "claims": []}


def _section(fx, unit_key, key, role="methods"):
    return {"section_key": key, "title": "合成章节 " + key, "role": role,
            "blocks": [{"type": "prose", "markdown": "配方中的固定章节说明。", "evidence_refs": [fx.ref(unit_key)]},
                       {"type": "unit", "ref": fx.ref(unit_key), "block_ids": ["m"]}],
            "watch_refs": [], "missing_refs": []}


def _document(fx, section_key, document_type):
    return {"document_type": document_type, "purpose": "合成固定文稿回归", "audience": "测试读者",
            "scope": SCOPE, "common_refs": [], "section_refs": [fx.ref(section_key)],
            "watch_refs": [], "missing_refs": []}


def _bootstrap(root, clock):
    """创建最小原生对象和受控原件；不写 memory/ 下的任何权威文件。"""
    _write_json(root / "workspace.json", {"schema_version": 1, "required_paths": []})
    _write_json(root / "tools" / "registry.json", {"schema_version": 1, "tools": []})
    for area in ("research", "projects"):
        shutil.copytree(REPOSITORY / area / "_template", root / area / "_template")
    descriptors = {"A": ("research", "mq-a", "合成温度反馈研究"),
                   "B": ("projects", "mq-b", "合成冷却与排队项目"),
                   "X": ("research", "mq-x", HIDDEN_TITLE)}
    owner_ids, native_paths, sources = {}, {}, {}
    for alias, (area, slug, title) in descriptors.items():
        creator = workspace_cli.create_research if area == "research" else workspace_cli.create_project
        with patch.object(workspace_cli, "now_utc", return_value=clock.value), redirect_stdout(io.StringIO()):
            directory = creator(root, slug, title)
        card = directory / ("research.json" if area == "research" else "project.json")
        data = json.loads(card.read_text(encoding="utf-8"))
        # 模板默认 restricted；只有刚创建且明确合成的 A/B 被设为 internal。
        # X 维持模板的限制状态，因此不能借规范写服务绕过其读取限制。
        data["sensitivity"] = "restricted" if alias == "X" else "internal"
        _write_json(card, data)
        owner_ids[alias] = data["research_id" if area == "research" else "project_id"]
        native_paths[alias] = card.relative_to(root).as_posix()
        original = directory / "data" / "原始 输入.txt"
        original.parent.mkdir(parents=True, exist_ok=True)
        text = HIDDEN_BODY if alias == "X" else f"MQ_{alias}_ORIGINAL\nSYNTHETIC ONLY：版本固定的软件测试输入。\n"
        original.write_text(text, encoding="utf-8")
        sources[alias] = {"source_id": "SRC-MQ-" + alias, "path": original.relative_to(root).as_posix(),
                          "enabled": True, "sensitivity": data["sensitivity"], "sha256": _hash(original)}
    _write_json(root / "retrieval" / "sources.json", {"schema_version": 1, "sources": list(sources.values())})
    run_ids = {}
    for alias in ("A", "B"):
        # 创建和登记调用都固定时钟/随机身份；Run 保持 planned，绝不伪造执行成功。
        with patch.object(workspace_cli, "now_utc", return_value=clock.value), \
                patch.object(workspace_cli.uuid, "uuid4", return_value=uuid.UUID(_uuid("run:" + alias))), \
                redirect_stdout(io.StringIO()):
            run_dir = workspace_cli.create_run(root, None, "SYNTHETIC ONLY " + alias, owner_id=owner_ids[alias])
        run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        run_ids[alias] = run["run_id"]
        with patch.object(run_capture, "timestamp", side_effect=clock), \
                patch.object(run_capture.uuid, "uuid4", return_value=uuid.UUID(_uuid("capture:" + alias))):
            run_capture.register(root, run["run_id"], inputs=[sources[alias]["path"]])
    return owner_ids, native_paths, sources, run_ids


def materialize(target, *, isolation_root):
    """构造新的隔离 F1，拒绝已有目标和正式工作区；失败残留可供审查。

    isolation_root 应来自 TemporaryDirectory；仓库内只允许 .local/ 或 tmp/。
    调用者拥有生命周期，本函数不自动删除目标，不修改旧冻结配方。
    """
    boundary, root = Path(isolation_root).resolve(), Path(target).resolve()
    permitted = (REPOSITORY / ".local", REPOSITORY / "tmp")
    if boundary == REPOSITORY or (boundary.is_relative_to(REPOSITORY)
                                  and not any(boundary.is_relative_to(path) for path in permitted)):
        raise ValueError("UNSAFE_PATH: isolation_root 不能是正式工作区")
    if root == boundary or not root.is_relative_to(boundary) or root.exists() or REPOSITORY.is_relative_to(root):
        raise ValueError("UNSAFE_PATH: target 必须是隔离根下尚不存在的子目录")
    root.mkdir(parents=True)
    (root / "SYNTHETIC_ONLY.txt").write_text(FIXTURE_VERSION + "\n", encoding="utf-8")
    clock = FixtureClock()
    owner_ids, native_paths, sources, run_ids = _bootstrap(root, clock)
    fx = MaterialQueryFixture(root, MemoryService(root, clock=clock, id_factory=_CommitIds()),
                              clock, owner_ids, sources, run_ids)

    # A/B 均具备 L0–L4。先建 B 的技术单元，使 A 能用合法 prerequisite 固定引用它。
    for alias in ("B", "A"):
        source = {"source_ref": fx.source_ref(alias), "acquisition": "original_link",
                  "completeness": "complete", "acquired_at": clock()}
        fx.commit_draft(alias + ".source", _draft(fx, alias, "source", alias + " 原始依据", source))
        unit_sources = [fx.source_ref(alias)]
        if alias == "A":
            unit_sources.append(fx.ref("B.unit", "prerequisite"))
        fx.commit_draft(alias + ".unit.r1", _draft(fx, alias, "detail", alias + " 反馈方法", _unit(fx, alias), sources=unit_sources))
        fx._remember(alias + ".unit", fx.records[alias + ".unit.r1"])

    fx.claims = {"accepted": "CLM-MQ-ACCEPTED", "unreviewed": "CLM-MQ-UNREVIEWED",
                 "stale": "CLM-MQ-STALE", "retracted": "CLM-MQ-RETRACTED", "superseded": "CLM-MQ-SUPERSEDED"}
    two_claims = [_claim(fx, "A", fx.claims["accepted"], "输入 A 是固定的合成文本"),
                  _claim(fx, "A", fx.claims["unreviewed"], "第二条主张尚无软件复核")]
    fx.commit_draft("A.event", _draft(fx, "A", "event", "A 失败事件与双主张", _event(fx, "A", two_claims, failed=True)))
    fx.review("A.review.accepted", "A.event", fx.claims["accepted"])
    fx.commit_draft("A.stale_event.r1", _draft(fx, "A", "event", "A 可变容器",
                    _event(fx, "A", [_claim(fx, "A", fx.claims["stale"], "主张文字不变，容器会修订")])) )
    fx.review("A.review.stale", "A.stale_event.r1", fx.claims["stale"])
    changed = deepcopy(fx.records["A.stale_event.r1"]["payload"])
    changed["observation"] = "MQ_CONTAINER_R2：补充了新的观察条件，旧复核必须失效"
    fx.revise("A.stale_event.r2", "A.stale_event.r1", payload=changed)
    fx._remember("A.stale_event", fx.records["A.stale_event.r2"])

    other_claims = [_claim(fx, "B", fx.claims[name], "合成 " + name) for name in ("retracted", "superseded")]
    fx.commit_draft("B.event", _draft(fx, "B", "event", "B 成功事件及历史复核", _event(fx, "B", other_claims)))
    fx.review("B.review.retracted.r1", "B.event", fx.claims["retracted"])
    fx.review("B.review.retracted.r2", "B.event", fx.claims["retracted"], "retracted")
    fx.review("B.review.superseded", "B.event", fx.claims["superseded"], "superseded", fx.claims["accepted"])

    experiences = [
        ("A.experience", "A", "延迟反馈回路中高增益导致振荡", "先获得时延，再逐级提高增益", True),
        ("A.conflict", "A", "对同一合成边界的冲突建议", "假设没有时延即可直接提高增益；此建议待反证", True),
        ("B.experience", "B", "冷却温度与执行器形成反馈回路", "限制增益并观察温度响应", False),
        ("C.no_edge_positive", "B", "队列长度经延迟观测后调节发送速率", "按负反馈降低拥塞，须重估时延和执行器", False),
        ("D.same_words_negative", "B", "反馈问卷与增益评分只作一次离线汇总", "这不是测量后干预的闭环，不能迁移控制增益", False)]
    for key, alias, problem, recommendation, failed in experiences:
        fx.commit_draft(key, _draft(fx, alias, "experience", key, _experience(problem, recommendation, failed=failed),
                                   body=problem + "。" + recommendation))

    fx.association("edge.current", "A.experience", "B.experience")
    fx.association("edge.old_unit", "A.unit.r1", "B.unit")
    for alias in ("A", "B"):
        result_refs = [fx.ref(alias + ".unit"), fx.ref(alias + ".event"), fx.ref(alias + ".experience")]
        payload = {"topic": "温度控制" if alias == "A" else "冷却与排队", "goal_refs": [], "route_refs": [],
                   "result_refs": result_refs, "question_refs": [],
                   "conflict_refs": [fx.ref("A.conflict", "contradicts")] if alias == "A" else [],
                   "next_steps": ["保留反证，检查可迁移边界"],
                   "coverage": {"owner_ids": [owner_ids[alias]], "source_versions": [fx.source_ref(alias)], "missing": []}}
        fx.commit_draft(alias + ".map", _draft(fx, alias, "map", alias + " 主题地图", payload, sources=result_refs))

    # 两份文稿最初固定同一旧单元；随后仅简报明确采用 r2，过程稿始终回读 r1。
    for key, doc_type, role in (("process", "research_process", "methods"), ("report", "research_report", "conclusion")):
        fx.commit_draft("A." + key + "_section.r1", _draft(fx, "A", "document_section", key + " 独立章节",
                        _section(fx, "A.unit.r1", key, role), sources=[fx.ref("A.unit.r1")]))
        fx.commit_draft("A." + key + ".r1", _draft(fx, "A", "document", key + " 独立文稿",
                        _document(fx, "A." + key + "_section.r1", doc_type), sources=[]))
        fx._remember("A." + key, fx.records["A." + key + ".r1"])
    fx.revise("A.unit.r2", "A.unit.r1", payload=_unit(fx, "A", revision=2))
    fx._remember("A.unit", fx.records["A.unit.r2"])
    fx.revise("A.report_section.r2", "A.report_section.r1", payload=_section(fx, "A.unit.r2", "report", "conclusion"),
              sources=[fx.ref("A.unit.r2")])
    fx.revise("A.report.r2", "A.report.r1", payload=_document(fx, "A.report_section.r2", "research_report"))
    fx._remember("A.report", fx.records["A.report.r2"])
    # 新反证在旧地图之后加入，故意没有指向 A 的旧依赖边；它只是后续维护测试输入。
    fx.commit_draft("B.new_counterevidence", _draft(fx, "B", "event", "新反证但无旧边", _event(fx, "B", unknown=True),
                    body="MQ_NEW_COUNTEREVIDENCE：合成死区会破坏先前线性反馈假设，需要重新检查边界。"))

    # 不把缺字段或断引用写成合法知识。后续测试可通过公开 validate-draft 注入。
    malformed = _draft(fx, "A", "detail", "缺必需摘要字段", _unit(fx, "A"))
    del malformed["payload"]["retrieval_description"]["limitations"]
    fx.invalid_drafts["missing_required_field"] = malformed
    broken = _draft(fx, "A", "document_section", "断开的固定引用", _section(fx, "A.unit.r1", "broken"))
    broken["payload"]["blocks"][1]["ref"]["target_id"] = "MEM-" + _uuid("missing-record")
    fx.invalid_drafts["broken_fixed_reference"] = broken
    fx.labels = {"positive_without_edge": "C.no_edge_positive", "lexical_negative": "D.same_words_negative",
                 "new_counterevidence_without_old_edge": "B.new_counterevidence",
                 "outcomes": {"A.event": "failure", "B.event": "success", "B.new_counterevidence": "unknown"},
                 "note": "这些是配方标注，不是实际 AI 旅程结果或未来接口的返回字段。"}
    fx.limits = [
        "F1 为最小稳定子集；未构造图环、菱形、全表示组合和真实向量故障矩阵。",
        "depends_on/similar_structure 等新名未写入旧 schema；使用 prerequisite/analogous_to 和文稿固定引用。",
        "Owner X 保持 restricted，仅含原生卡片与原件；公开服务拒绝向不可读 owner 提交规范内容。",
        "缺字段和断边仅作为未提交故障输入；没有绕过 schema、伪造 claim/review 或手写 HEAD。",
        "Run 保持 planned；review 仅验证合成软件契约，不表示执行过领域实验或实际 AI 评估。",
        "本 fixture 未配置向量后端；真实 FTS 和版本存储可用，向量/索引故障由使用者另行注入。"]
    # Reading now discovers Owners only through the independent compressed
    # projection.  Production commits merely mark it pending; this synthetic
    # fixture explicitly performs the same maintenance action a prepared
    # workspace would run, with vectors disabled for deterministic tests.
    from memory import discovery, index
    catalog = index.Catalog(root)
    for owner_id in (owner_ids['A'], owner_ids['B']):
        head = catalog.snapshot(owner_id)['head']
        discovery.rebuild_owner(root, owner_id, head,
            projection_version=discovery.PROJECTION_VERSION, vector='off')
    inputs = {source["path"]: _hash(root / source["path"]) for source in sources.values()}
    inputs.update({path: _hash(root / path) for path in native_paths.values()})
    manifest = {"schema_version": 1, "fixture_version": FIXTURE_VERSION, "synthetic_only": True,
                "generator_sha256": _hash(Path(__file__)),
                "memory_schema_sha256": _hash(REPOSITORY / "automation/schemas/memory-v3.schema.json"),
                "owner_ids": fx.owner_ids, "run_ids": fx.run_ids, "record_ids": fx.record_ids,
                "fixed_refs": fx.refs, "claims": fx.claims, "input_files": inputs,
                "labels": fx.labels, "limits": fx.limits}
    _write_json(root / "material-query-fixture.json", manifest)
    return fx
