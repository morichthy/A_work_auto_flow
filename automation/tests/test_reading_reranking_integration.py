"""Coordinator-level contracts for fixed-context retrieve → rerank delivery.

This suite uses the ordinary synthetic material store and only replaces the
Cross-encoder provider.  It therefore tests authorization, fixed packets,
session persistence and ledger behavior around the real reading entry points.
"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from material_query_fixture import materialize
from test_memory_documents_v3 import unit_payload
from memory import contracts
from material_query.api import dispatch
from material_query.budget import DEFAULT_BUDGET
from material_query.contracts import AssociationOptions, DefinitionRef, QueryRequest, Scope
from material_query.coordinator import Coordinator
from material_query.wire import json_value


class Provider:
    """A controllable scorer which records complete model inputs, never model quality."""
    identity = {"model": "integration-fake", "sha256": "1" * 64}
    max_length = 100_000

    def __init__(self):
        self.pairs = []

    def count_tokens(self, question, text):
        return len(question) + len(text)

    def score_pairs(self, pairs):
        self.pairs.extend(pairs)
        # The second experience is deliberately lower in raw RRF but contains
        # this full-body marker, letting the test observe an actual promotion.
        return [10.0 if "KEEP_SHORT_END" in text else 0.0 for _, text in pairs]


class ReadingRerankingIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.TemporaryDirectory()
        cls.fx = materialize(Path(cls.base.name) / "重排 阅读模板", isolation_root=cls.base.name)
        draft = {key: deepcopy(cls.fx.records["A.unit"][key]) for key in
                 (*contracts.CONTENT_FIELDS, "schema_version", "record_reason")}
        draft.update(title="重排固定技术单元", body_markdown="", payload=unit_payload(),
                     sources=[cls.fx.source_ref("A")], keywords=["readingfixture"])
        draft["payload"]["blocks"][1]["markdown"] += " readingfixture"
        cls.fx.commit_draft("reranking.unit", draft)
        draft = {key: deepcopy(cls.fx.records["A.experience"][key]) for key in
                 (*contracts.CONTENT_FIELDS, "schema_version", "record_reason")}
        draft.update(title="readingfixture 原始经验", body_markdown="普通候选正文",
                     keywords=["readingfixture"], sources=[cls.fx.source_ref("A")])
        cls.fx.commit_draft("reranking.experience.first", draft)
        draft.update(title="readingfixture 正确经验", body_markdown="完整必要上下文 KEEP_SHORT_END",
                     keywords=["readingfixture"])
        cls.fx.commit_draft("reranking.experience.correct", draft)
        # Three rows make two continuations observable when result_limit=1;
        # the final continuation must still pin the original scorer identity.
        draft.update(title="readingfixture 第三经验", body_markdown="第三个普通候选正文")
        cls.fx.commit_draft("reranking.experience.third", draft)

    @classmethod
    def tearDownClass(cls):
        cls.base.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "重排 阅读副本"
        shutil.copytree(self.fx.root, self.root)
        self.app = Coordinator(self.root)
        self.sid = "RS-" + str(uuid.uuid4())
        self.scope = Scope((self.fx.owner_ids["A"],), None, None, None, None, None, None, False, (), (), None, None)
        budget = replace(DEFAULT_BUDGET, model_calls=20, model_tokens=20_000,
                         model_input_tokens=20_000, rerank_items=100)
        self.query = QueryRequest(DefinitionRef("full", "1"), "readingfixture", (), self.scope, self.scope,
            "exploration", AssociationOptions("off", "existing-relations", "1", 2, .15, None),
            budget, "current", 1, "skip", (), "")
        self.revision = 1

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def start(self, reranking=None):
        raw = {"session_id": self.sid, "goal": "重排端到端", "conditions": [], "query": json_value(self.query)}
        if reranking is not None:
            raw["reranking"] = reranking
        result = dispatch(self.app, "reading-start", raw)
        self.assertEqual(result["status"], "ok", result)

    def call(self, action, *, request_id=None, expected_revision=None, **fields):
        result = dispatch(self.app, "reading-" + action, {"session_id": self.sid,
            "expected_revision": self.revision if expected_revision is None else expected_revision,
            "request_id": request_id or str(uuid.uuid4()), **fields})
        if (result.get("value") or {}).get("revision"):
            self.revision = result["value"]["revision"]
        return result

    def recall_fields(self, **extra):
        return {"question": "readingfixture", "keywords": [], "scope": json_value(self.scope),
                "reason": "固定候选重排", **extra}

    def test_candidate_window_promotes_later_correct_item_and_uses_complete_context(self):
        provider = Provider()
        self.start({"mode": "auto", "candidate_limit": 30, "conditions": [
            {"id": "model", "kind": "literal", "field": "型号", "expected": "X", "operator": "eq"}]})
        with patch("material_query.reranking.load_provider", return_value=provider):
            result = self.call("recall", **self.recall_fields())
        self.assertIn(result["status"], {"ok", "partial"}, result)
        overview = next(item for item in result["value"]["candidates"] if item["source"] == "overview_experience")
        ranking_diagnostics = {
            "coverage": result["value"]["coverage"],
            "gaps": result["value"]["gaps"],
            "provider_pair_count": len(provider.pairs),
            "candidate_rankings": [{"title": item["title"], "source": item["source"],
                                    "ranking": item.get("ranking")} for item in result["value"]["candidates"]],
        }
        self.assertIn("KEEP_SHORT_END", json.dumps(overview["packet"], ensure_ascii=False), ranking_diagnostics)
        self.assertGreater(overview["ranking"]["original_rank"], overview["ranking"]["final_rank"])
        self.assertEqual(overview["ranking"]["final_rank"], 1)
        self.assertEqual(overview["ranking"]["conditions"][0]["id"], "model")
        sent = "\n".join(text for _, text in provider.pairs)
        # These markers occur only in the assembled required definitions/body,
        # not in the 240-character display excerpt.
        self.assertIn("ONLY_FULL_RESULT", sent)
        self.assertIn("ONLY_DEFINITION", sent)
        rankings = [lane["ranking"] for lane in result["value"]["coverage"]["lanes"] if "ranking" in lane]
        self.assertTrue(rankings)
        self.assertTrue(all(row["status"] == "reranked" for row in rankings))
        # Model identity and phase timing must be available in the pageable
        # coverage rather than only in an ephemeral provider object.
        self.assertTrue(all(row["model"] == provider.identity for row in rankings))
        self.assertTrue(all("model_load_ms" in row and "inference_ms" in row and "total_ms" in row for row in rankings))

    def test_legacy_off_never_loads_provider(self):
        self.start()  # Omitted option remains the legacy off behavior.
        with patch("material_query.reranking.load_provider", side_effect=AssertionError("must stay off")):
            result = self.call("recall", **self.recall_fields())
        self.assertIn(result["status"], {"ok", "partial"}, result)
        self.assertTrue(all("ranking" not in item for item in result["value"]["candidates"]))

    def test_required_missing_model_fails_but_persists_ledger(self):
        self.start({"mode": "required", "candidate_limit": 30, "conditions": []})
        with patch("material_query.reranking.load_provider", side_effect=ValueError("absent")):
            failed = self.call("recall", **self.recall_fields())
        self.assertEqual(failed["code"], "UNSUPPORTED", failed)
        self.assertGreater(failed["consumed"]["read_bytes"], 0)
        self.assertEqual(self.revision, 1, "failed mutation must not advance the session revision")

    def test_auto_missing_model_falls_back_to_original_order(self):
        self.start({"mode": "auto", "candidate_limit": 30, "conditions": []})
        with patch("material_query.reranking.load_provider", side_effect=ValueError("absent")):
            result = self.call("recall", **self.recall_fields())
        self.assertIn(result["status"], {"ok", "partial"}, result)
        self.assertTrue(any("Cross-encoder" in gap for gap in result["value"]["gaps"]))
        for item in result["value"]["candidates"]:
            self.assertEqual(item["ranking"]["original_rank"], item["ranking"]["final_rank"])

    def test_page_freezes_strategy_and_changed_provider_cannot_silently_rerank(self):
        first, changed = Provider(), Provider()
        changed.identity = {"model": "integration-fake-new", "sha256": "2" * 64}
        self.start({"mode": "auto", "candidate_limit": 30, "conditions": []})
        with patch("material_query.reranking.load_provider", return_value=first):
            recalled = self.call("recall", **self.recall_fields())
        self.assertTrue(any(lane["has_more"] for lane in recalled["value"]["coverage"]["lanes"]))
        with patch("material_query.reranking.load_provider", return_value=changed):
            page = self.call("page")
        self.assertIn(page["status"], {"ok", "partial"}, page)
        for lane in page["value"]["coverage"]["lanes"]:
            if "ranking" not in lane:
                continue
            self.assertEqual(lane["ranking"]["status"], "fallback")
            self.assertEqual(lane["ranking"]["model"], first.identity)
            self.assertEqual(lane["ranking"]["attempted_model"], changed.identity)
        # The candidate window can have more than two pages.  A changed model
        # must remain incompatible with the frozen first round; page two must
        # not accept it merely because page one recorded the fallback model.
        with patch("material_query.reranking.load_provider", return_value=changed):
            second_page = self.call("page")
        self.assertIn(second_page["status"], {"ok", "partial"}, second_page)
        for lane in second_page["value"]["coverage"]["lanes"]:
            if "ranking" not in lane:
                continue
            self.assertEqual(lane["ranking"]["status"], "fallback")

    def test_retry_is_idempotent_and_revoked_source_does_not_leak(self):
        provider = Provider()
        self.start({"mode": "auto", "candidate_limit": 30, "conditions": []})
        request_id = str(uuid.uuid4())
        original_revision = self.revision
        with patch("material_query.reranking.load_provider", return_value=provider):
            first = self.call("recall", request_id=request_id, **self.recall_fields())
            calls = len(provider.pairs)
            replay = self.call("recall", request_id=request_id, expected_revision=original_revision,
                               **self.recall_fields())
        self.assertTrue(replay["value"]["replayed"])
        self.assertEqual(len(provider.pairs), calls)
        catalog = self.root / "retrieval" / "sources.json"
        source_data = json.loads(catalog.read_text(encoding="utf-8"))
        for source in source_data["sources"]:
            source["enabled"] = False
        catalog.write_text(json.dumps(source_data), encoding="utf-8")
        denied = self.call("resume")
        self.assertNotEqual(denied["status"], "ok")
        self.assertNotIn("KEEP_SHORT_END", json.dumps(denied, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
