"""独立 Owner discovery 投影的合成契约测试。

这些用例只验证派生表、水位、版本拒绝和结构缺口；不把测试排序解释为
现实召回质量。全部数据位于 TemporaryDirectory，不读取业务材料。
"""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "automation/scripts"))

from memory import api, cli, discovery, index, owners
from memory.errors import MemoryError
from memory.service import MemoryService
from memory.store import MemoryStore


def _base(owner_id, kind, title, body, payload, *, version):
    return {
        "schema_version": version,
        "owner_id": owner_id,
        "kind": kind,
        "title": "SYNTHETIC ONLY " + title,
        "body_markdown": body,
        "keywords": ["SYNTHETIC", kind],
        "payload": deepcopy(payload),
        "sources": [],
        "provenance_gap": "SYNTHETIC ONLY 软件契约数据，没有现实依据",
        "record_reason": "验证独立 discovery 投影",
        "discovery": "workspace_summary",
        "sensitivity": "internal",
    }


def _overview(owner_id):
    return _base(owner_id, "overview", "概览 DISCOVERY_OVERVIEW", "DISCOVERY_OVERVIEW 自足概览正文", {
        "question": "如何验证压缩发现",
        "methods": ["固定合成输入"],
        "results": ["只验证软件边界"],
        "current_stage": "合成验收",
        "limitations": ["不能推断实际检索质量"],
        "open_questions": [],
        "experience_refs": [],
        "claims": [],
        "process_refs": [],
        "technical_refs": [],
    }, version=4)


def _experience(owner_id):
    return _base(owner_id, "experience", "经验 DISCOVERY_EXPERIENCE", "DISCOVERY_EXPERIENCE 可迁移边界", {
        "problem_structure": "重复正文可能挤占其他对象",
        "recommendation": "先按 Owner 融合",
        "applicable": ["合成发现流程"],
        "prohibited": ["不能当作科学证据"],
        "failure_modes": ["错误联想"],
        "retry_conditions": [],
        "claim_refs": [],
        "claims": [],
        "knowledge_type": "recommendation",
        "process_refs": [],
        "technical_refs": [],
    }, version=4)


def _narrative(owner_id):
    return _base(owner_id, "narrative", "过程 DISCOVERY_NARRATIVE", "ZZZNARRATIVEONLY888 不应进入发现投影", {
        "question": "DISCOVERY_NARRATIVE_QUESTION 为什么失败",
        "stages": [{"situation": "DISCOVERY_STAGE 情境", "action": "正文动作不进入紧凑面",
                    "reason": "DISCOVERY_REASON 原因", "outcome": "DISCOVERY_OUTCOME 结果", "evidence_refs": []}],
        "experience_refs": [],
        "limitations": ["DISCOVERY_LIMITATION 限制"],
        "claims": [],
        "process_refs": [],
        "technical_refs": [],
    }, version=4)


def _detail(owner_id):
    return _base(owner_id, "detail", "技术单元 DISCOVERY_DETAIL", "", {
        "unit_type": "method",
        "retrieval_description": {
            "question": "DISCOVERY_DETAIL_QUESTION 如何定义",
            "method": "DISCOVERY_DETAIL_METHOD 使用固定换算",
            "key_findings": ["DISCOVERY_DETAIL_FINDING 只验证投影"],
            "applicable": ["合成输入"],
            "not_applicable": ["现实测量"],
            "limitations": ["没有实验"],
        },
        "run_ref": None,
        "evidence_refs": [],
        "blocks": [{"block_id": "long", "role": "methods",
                    "markdown": "ZZZBLOCKONLY777 " + "长正文 " * 700, "requires_block_ids": []}],
        "figures": [],
        "missing_refs": [],
    }, version=3)


def _legacy_detail(owner_id, run_sha):
    """合法旧 L1 没有 retrieval_description，供确定性 gap 检查。"""
    return _base(owner_id, "detail", "旧技术记录", "LEGACY_DETAIL_FULL_TEXT", {
        "run_ref": {"target_kind": "owner", "target_id": "RUN-DISCOVERY", "revision": None,
                    "sha256": run_sha, "locator": "run.json", "relation": "input"},
        "question": "旧问题",
        "method": "旧方法",
        "steps": ["旧步骤"],
        "inputs": [],
        "parameters": [],
        "formulas": [],
        "figures": [],
        "results": "旧结果",
        "limitations": ["旧限制"],
        "missing_refs": [],
    }, version=2)


class DeterministicDiscoveryVector:
    """只模拟 discovery collection 协议，不声称语义效果。"""
    storage = {}
    collection = "synthetic_memory_discovery_v1"

    def __init__(self, root):
        self.entries = self.storage.setdefault(str(Path(root).resolve()), {})

    def close(self):
        pass

    def sync_owner(self, owner_id, entries, *, fault=lambda _point: None):
        old = {key for key, row in self.entries.items() if row["owner_id"] == owner_id}
        current = {row["entry_id"] for row in entries}
        for key in old - current:
            del self.entries[key]
        for row in entries:
            fault("vector_upsert")
            self.entries[row["entry_id"]] = deepcopy(row)
        return {"collection": self.collection, "points": len(current)}

    def search(self, query, allowed_ids):
        return [{**row, "vector_score": 0.75} for key, row in sorted(self.entries.items()) if key in allowed_ids]


class MemoryDiscoveryIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Owner发现索引 合成-")
        self.root = Path(self.temp.name)
        for oid in ("RES-DISCOVERY", "RES-GAP"):
            card = self.root / "research" / oid / "research.json"
            card.parent.mkdir(parents=True)
            card.write_text(json.dumps({"schema_version": 1, "research_id": oid,
                "title": "SYNTHETIC ONLY " + oid, "keywords": ["OWNER_METADATA_TERM"],
                "sensitivity": "internal", "claims": [], "dependencies": []}), encoding="utf-8")
        run = self.root / "runs" / "discovery" / "run.json"
        run.parent.mkdir(parents=True)
        run.write_text(json.dumps({"schema_version": 1, "run_id": "RUN-DISCOVERY",
            "title": "SYNTHETIC ONLY discovery run", "status": "planned",
            "claims": [], "dependencies": []}), encoding="utf-8")
        (self.root / "workspace.json").write_text('{"schema_version":1}', encoding="utf-8")
        self.service = MemoryService(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def commit(self, owner_id, drafts, *, head=None):
        operations = [{"op": "put_record", "client_key": "r" + str(i), "draft": draft}
                      for i, draft in enumerate(drafts)]
        request = {"schema_version": 1, "request_id": str(uuid.uuid4()),
            "actor": {"kind": "workflow", "id": "synthetic-discovery-test"},
            "owner_id": owner_id, "expected_head": head, "operations": operations}
        return self.service.commit(request)

    def head(self, owner_id):
        owner = owners.resolve_owner(self.root, owner_id)
        return MemoryStore(self.root).read_snapshot(owner)["head"]

    def test_independent_projection_uses_only_compressed_discovery_surfaces(self):
        self.commit("RES-DISCOVERY", [_overview("RES-DISCOVERY"), _experience("RES-DISCOVERY"),
            _narrative("RES-DISCOVERY"), _detail("RES-DISCOVERY")])
        before = discovery.search(self.root, "DISCOVERY_OVERVIEW", channel="lexical")
        self.assertEqual(before["status"], "unavailable")
        self.assertEqual(before["hits"], [])

        built = discovery.rebuild_owner(self.root, "RES-DISCOVERY", self.head("RES-DISCOVERY"),
            projection_version=discovery.PROJECTION_VERSION, vector="off")
        self.assertEqual(built["index_status"], "indexed", built)
        with closing(index.connect(self.root)) as db:
            rows = [dict(row) for row in db.execute(
                "SELECT source_level,source_kind,text,fixed_ref FROM memory_discovery_entries WHERE owner_id=? ORDER BY projection_id",
                ("RES-DISCOVERY",))]
            self.assertEqual({row["source_level"] for row in rows}, {None, "L1", "L2", "L3", "L4"})
            self.assertFalse(any("ZZZBLOCKONLY777" in row["text"] for row in rows))
            self.assertFalse(any("ZZZNARRATIVEONLY888" in row["text"] for row in rows))
            self.assertGreater(db.execute("SELECT COUNT(*) FROM memory_entries WHERE text LIKE '%ZZZBLOCKONLY777%'").fetchone()[0], 0)

        for term, level in (("DISCOVERY_OVERVIEW", "L4"), ("DISCOVERY_EXPERIENCE", "L3"),
                            ("DISCOVERY_REASON", "L2"), ("DISCOVERY_DETAIL_METHOD", "L1"),
                            ("OWNER_METADATA_TERM", None)):
            result = discovery.search(self.root, term, owner_ids=["RES-DISCOVERY"], channel="lexical")
            self.assertEqual(result["status"], "ready", result)
            self.assertTrue(any(hit["source_level"] == level for hit in result["hits"]), (term, result))
            self.assertTrue(all(hit["fixed_ref"]["target_id"] for hit in result["hits"]))
            for hit in (item for item in result['hits'] if item['fixed_ref']['target_kind'] == 'record'):
                ref = hit['fixed_ref']
                record = MemoryStore(self.root).read_record(
                    owners.resolve_owner(self.root, hit['owner_id']), ref['target_id'], ref['revision'])
                self.assertEqual(ref['sha256'], record['record_hash'])
        for secret in ("ZZZBLOCKONLY777", "ZZZNARRATIVEONLY888"):
            self.assertEqual(discovery.search(self.root, secret, owner_ids=["RES-DISCOVERY"], channel="lexical")["hits"], [])

    def test_rebuild_is_idempotent_and_refuses_changed_head(self):
        receipt = self.commit("RES-DISCOVERY", [_overview("RES-DISCOVERY")])
        original_head = self.head("RES-DISCOVERY")
        first = discovery.rebuild_owner(self.root, "RES-DISCOVERY", original_head,
            projection_version=discovery.PROJECTION_VERSION, vector="off")
        second = discovery.rebuild_owner(self.root, "RES-DISCOVERY", original_head,
            projection_version=discovery.PROJECTION_VERSION, vector="off")
        self.assertFalse(first["lexical"].get("unchanged", False))
        self.assertTrue(second["lexical"]["unchanged"])

        changed = _overview("RES-DISCOVERY")
        changed["body_markdown"] = "NEW_HEAD_ONLY_TERM"
        changed["change_reason"] = "合成修订"
        rid = receipt["record_results"][0]["record_id"]
        request = {"schema_version": 1, "request_id": str(uuid.uuid4()),
            "actor": {"kind": "workflow", "id": "synthetic-discovery-test"},
            "owner_id": "RES-DISCOVERY", "expected_head": original_head["commit_id"],
            "operations": [{"op": "put_record", "record_id": rid, "expected_revision": 1, "draft": changed}]}
        self.service.commit(request)
        pending = discovery.status(self.root, "RES-DISCOVERY")
        self.assertEqual(pending["lexical"], "pending")
        self.assertEqual(pending["vector"], "pending")
        stale = discovery.rebuild_owner(self.root, "RES-DISCOVERY", original_head,
            projection_version=discovery.PROJECTION_VERSION, vector="off")
        self.assertEqual(stale["index_status"], "stale")
        self.assertEqual(discovery.search(self.root, "NEW_HEAD_ONLY_TERM", owner_ids=["RES-DISCOVERY"])["hits"], [])

    def test_lexical_and_vector_watermarks_fail_independently(self):
        self.commit("RES-DISCOVERY", [_overview("RES-DISCOVERY")])
        head = self.head("RES-DISCOVERY")

        def failure(point):
            if point == "vector_upsert":
                raise OSError("SYNTHETIC ONLY vector failure")

        failed = discovery.rebuild_owner(self.root, "RES-DISCOVERY", head,
            projection_version=discovery.PROJECTION_VERSION, vector="auto",
            backend_factory=DeterministicDiscoveryVector, fault=failure)
        self.assertEqual(failed["lexical"]["status"], "indexed")
        self.assertEqual(failed["vector"]["status"], "failed")
        self.assertEqual(failed["index_status"], "pending")
        canonical_before = MemoryStore(self.root).read_snapshot(owners.resolve_owner(self.root, "RES-DISCOVERY"))
        repaired = discovery.rebuild_owner(self.root, "RES-DISCOVERY", head,
            projection_version=discovery.PROJECTION_VERSION, vector="auto",
            backend_factory=DeterministicDiscoveryVector)
        self.assertEqual(repaired["index_status"], "indexed", repaired)
        self.assertTrue(repaired["lexical"]["unchanged"])
        canonical_after = MemoryStore(self.root).read_snapshot(owners.resolve_owner(self.root, "RES-DISCOVERY"))
        self.assertEqual(canonical_after, canonical_before)

    def test_gaps_are_structural_and_projection_readiness_is_separate(self):
        run_sha = index.Catalog(self.root).graph().nodes["RUN-DISCOVERY"]["fingerprint"]
        self.commit("RES-GAP", [_legacy_detail("RES-GAP", run_sha)])
        before = discovery.gaps(self.root, "RES-GAP")
        codes = {gap["code"] for gap in before["owners"][0]["gaps"]}
        self.assertIn("MISSING_L4", codes)
        self.assertIn("L1_RETRIEVAL_DESCRIPTION_MISSING", codes)
        self.assertIn("DISCOVERY_INDEX_NOT_READY", codes)

        head = self.head("RES-GAP")
        discovery.rebuild_owner(self.root, "RES-GAP", head,
            projection_version=discovery.PROJECTION_VERSION, vector="off")
        after = discovery.gaps(self.root, "RES-GAP")
        codes = {gap["code"] for gap in after["owners"][0]["gaps"]}
        self.assertIn("MISSING_L4", codes)
        self.assertIn("L1_RETRIEVAL_DESCRIPTION_MISSING", codes)
        self.assertNotIn("DISCOVERY_INDEX_NOT_READY", codes)

        # Structure code must not guess that a nonempty authored description is
        # semantically incomplete.  That judgement belongs to the low-grade
        # model after full reading.
        self.assertFalse(discovery._description_absent({"question": "已有非空说明"}))

    def test_discovery_vector_backend_uses_a_separate_collection_namespace(self):
        with patch.object(index.MemoryVectorBackend, "__init__", return_value=None) as initialize:
            discovery.DiscoveryVectorBackend(self.root)
        initialize.assert_called_once_with(self.root, None,
            collection_prefix=discovery.COLLECTION_PREFIX, encoder_version=discovery.ENCODER_VERSION)
        self.assertNotEqual(discovery.COLLECTION_PREFIX, "memory_v1")

    def test_public_memory_actions_expose_gap_and_rebuild_without_canonical_writes(self):
        self.commit("RES-DISCOVERY", [_overview("RES-DISCOVERY")])
        head = self.head("RES-DISCOVERY")
        self.assertIn("rebuild-discovery", api.ACTIONS)
        self.assertIn("discovery-gaps", api.ACTIONS)
        parsed = cli.parser().parse_args(["rebuild-discovery", "--request", "synthetic.json", "--dry-run"])
        self.assertEqual(parsed.action, "rebuild-discovery")
        preview = api.dispatch(self.service, "rebuild-discovery", {"owner_id": "RES-DISCOVERY",
            "expected_head": head, "projection_version": discovery.PROJECTION_VERSION,
            "vector": "off", "dry_run": True})
        self.assertTrue(preview["dry_run"])
        self.assertEqual(preview["writes"], 0)
        with closing(index.connect(self.root)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM memory_discovery_entries").fetchone()[0], 0)
        built = api.dispatch(self.service, "rebuild-discovery", {"owner_id": "RES-DISCOVERY",
            "expected_head": head, "projection_version": discovery.PROJECTION_VERSION, "vector": "off"})
        self.assertEqual(built["index_status"], "indexed")
        gaps = api.dispatch(self.service, "discovery-gaps", {"owner_id": "RES-DISCOVERY"})
        self.assertEqual(gaps["owners"][0]["owner_id"], "RES-DISCOVERY")

    def test_projection_version_is_explicit_and_fulltext_tables_are_untouched(self):
        self.commit("RES-DISCOVERY", [_overview("RES-DISCOVERY")])
        with closing(index.connect(self.root)) as db:
            full_before = [tuple(row) for row in db.execute("SELECT entry_id,signature FROM memory_entries ORDER BY entry_id")]
        with self.assertRaises(MemoryError) as caught:
            discovery.rebuild_owner(self.root, "RES-DISCOVERY", self.head("RES-DISCOVERY"),
                projection_version="wrong-version", vector="off")
        self.assertEqual(caught.exception.code, "INVALID_ARGUMENT")
        discovery.rebuild_owner(self.root, "RES-DISCOVERY", self.head("RES-DISCOVERY"),
            projection_version=discovery.PROJECTION_VERSION, vector="off")
        with closing(index.connect(self.root)) as db:
            full_after = [tuple(row) for row in db.execute("SELECT entry_id,signature FROM memory_entries ORDER BY entry_id")]
            db.execute("DELETE FROM memory_discovery_fts")
            db.commit()
        self.assertEqual(full_after, full_before)
        missing = discovery.search(self.root, "DISCOVERY_OVERVIEW", owner_ids=["RES-DISCOVERY"])
        self.assertEqual(missing["status"], "unavailable")
        self.assertEqual(missing["hits"], [])

    def test_query_rechecks_external_source_permission_after_indexing(self):
        source = self.root / "synthetic-discovery-source.txt"
        source.write_text("SYNTHETIC ONLY source", encoding="utf-8")
        registry = self.root / "retrieval" / "sources.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registration = {"schema_version": 1, "sources": [{"source_id": "SRC-DISCOVERY",
            "path": source.name, "enabled": True, "sensitivity": "internal"}]}
        registry.write_text(json.dumps(registration), encoding="utf-8")
        record = _overview("RES-DISCOVERY")
        record["body_markdown"] += " ONLYOVERVIEW999"
        record["sources"] = [{"target_kind": "file", "target_id": "SRC-DISCOVERY",
            "revision": None, "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "locator": "完整", "relation": "derived_from"}]
        record["provenance_gap"] = None
        self.commit("RES-DISCOVERY", [record])
        discovery.rebuild_owner(self.root, "RES-DISCOVERY", self.head("RES-DISCOVERY"),
            projection_version=discovery.PROJECTION_VERSION, vector="off")
        self.assertTrue(discovery.search(self.root, "ONLYOVERVIEW999",
            owner_ids=["RES-DISCOVERY"])["hits"])
        registration["sources"][0]["enabled"] = False
        registry.write_text(json.dumps(registration), encoding="utf-8")
        self.assertEqual(discovery.search(self.root, "ONLYOVERVIEW999",
            owner_ids=["RES-DISCOVERY"])["hits"], [])

    def test_canonical_commit_invalidates_discovery_before_full_index_failure(self):
        receipt = self.commit("RES-DISCOVERY", [_overview("RES-DISCOVERY")])
        head = self.head("RES-DISCOVERY")
        discovery.rebuild_owner(self.root, "RES-DISCOVERY", head,
            projection_version=discovery.PROJECTION_VERSION, vector="off")
        self.assertEqual(discovery.status(self.root, "RES-DISCOVERY")["index_status"], "indexed")

        changed = _overview("RES-DISCOVERY")
        changed["body_markdown"] = "FULL_INDEX_FAILURE_NEW_HEAD"
        changed["change_reason"] = "合成修订验证失效顺序"
        request = {"schema_version": 1, "request_id": str(uuid.uuid4()),
            "actor": {"kind": "workflow", "id": "synthetic-discovery-test"},
            "owner_id": "RES-DISCOVERY", "expected_head": head["commit_id"],
            "operations": [{"op": "put_record", "record_id": receipt["record_results"][0]["record_id"],
                            "expected_revision": 1, "draft": changed}]}
        with patch.object(index, "sync_owner", side_effect=OSError("SYNTHETIC ONLY full index failure")):
            result = self.service.commit(request)
        self.assertEqual(result["save_status"], "committed")
        self.assertEqual(result["index_status"], "pending")
        state = discovery.status(self.root, "RES-DISCOVERY")
        self.assertEqual(state["lexical"], "pending")
        self.assertEqual(state["vector"], "pending")
        self.assertEqual(discovery.search(self.root, "DISCOVERY_OVERVIEW",
            owner_ids=["RES-DISCOVERY"])["hits"], [])


if __name__ == "__main__":
    unittest.main()
