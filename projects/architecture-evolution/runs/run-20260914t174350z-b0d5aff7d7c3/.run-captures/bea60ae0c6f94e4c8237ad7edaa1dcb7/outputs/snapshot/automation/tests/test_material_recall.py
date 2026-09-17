"""真实 F1 上的增量召回、独立通道和表示诊断回归。

规范记录/表示均通过公开 Memory API 保存。物理正文探针只包装实际
MeteredStore._record；SQLite 故障仅注入查询连接，未用假返回候选替代召回。
每个测试复制已验证的合成工作区，避免损坏水位或改版影响其他测试。
"""
from copy import copy, deepcopy
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import shutil
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from material_query_fixture import materialize, SCOPE
from memory import contracts as memory_contracts, index
from memory.service import MemoryService
from material_query.budget import DEFAULT_BUDGET
from material_query.contracts import AssociationOptions, AssembleRequest, DefinitionRef, FixedRef, QueryRequest, Scope
from material_query.coordinator import Coordinator
from material_query.legacy_adapter import from_legacy
from material_query.reader import MeteredStore
from material_query.wire import json_value


class MaterialRecallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.TemporaryDirectory()
        cls.template = materialize(Path(cls.base.name) / "增量召回 F1", isolation_root=cls.base.name)
        fx = cls.template
        # Three independent records share a search token and need only the
        # registered A original, so reading B/unrelated bodies is unnecessary.
        for number in range(3):
            draft = {key: deepcopy(fx.records["A.experience"][key]) for key in
                     (*memory_contracts.CONTENT_FIELDS, "schema_version", "record_reason")}
            draft.update(title=f"SYNTHETIC ONLY lazy page {number}",
                         body_markdown=f"zqxjpageunique canonical body {number}",
                         keywords=["zqxjpageunique"], sources=[fx.source_ref("A")])
            fx.commit_draft("lazy." + str(number), draft)
        # One canonical record has two authored searchable representations.
        # Their different lengths/frequencies yield independent BM25 scores.
        target = fx.ref("lazy.0", "derived_from")
        for slot, text in (("problem", "zqxjrepresentationunique " * 4),
                           ("result", "zqxjrepresentationunique explanation with extra words")):
            draft = {"schema_version": 3, "owner_id": fx.owner_ids["A"], "kind": "representation",
                     "title": "SYNTHETIC ONLY " + slot, "body_markdown": "", "keywords": [],
                     "sources": [target], "provenance_gap": None,
                     "record_reason": "SYNTHETIC ONLY 独立表示分数回归",
                     "discovery": "workspace_summary", "sensitivity": "internal",
                     "payload": {"target": target, "slot": slot, "text": text, "boundary_refs": []}}
            fx.commit_draft("representation." + slot, draft)

    @classmethod
    def tearDownClass(cls):
        cls.base.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "隔离 召回"
        shutil.copytree(self.template.root, self.root)
        self.fx = copy(self.template)
        self.fx.root, self.fx.service = self.root, MemoryService(self.root)
        self.fx.records, self.fx.refs = deepcopy(self.template.records), deepcopy(self.template.refs)
        self.fx.record_ids, self.fx.receipts = dict(self.template.record_ids), []
        self.fx.clock = deepcopy(self.template.clock)
        self.app = Coordinator(self.root)
        scope = Scope((self.fx.owner_ids["A"],), None, None, None, None, None, None, False, (), (), None, None)
        self.request = QueryRequest(DefinitionRef("full", "1"), "zqxjpageunique", (), scope, scope,
            "exploration", AssociationOptions("off", "existing-relations", "1", 2, 0.15, None),
            DEFAULT_BUDGET, "current", 1, "skip", (), "", channels=("lexical",), ranking_strategy="rrf")
        self.lazy_ids = {self.fx.record_ids["lazy." + str(n)] for n in range(3)}
        self.reads = []
        real_read = MeteredStore._record

        def observed(store, owner, record_id, entry):
            self.reads.append((record_id, entry["revision"]))
            return real_read(store, owner, record_id, entry)

        self.probe = patch.object(MeteredStore, "_record", observed)
        self.probe.start()

    def tearDown(self):
        self.probe.stop()
        self.app.close()
        self.temporary.cleanup()

    def search(self, request=None):
        result = self.app.search(json_value(request or self.request))
        self.assertIn(result["status"], {"ok", "partial"}, result)
        self.assertIsNotNone(result["value"], result)
        return result

    def first(self, result):
        rows = result["value"]["candidates"]
        self.assertEqual(len(rows), 1, result)
        return rows[0]

    def order(self):
        result = self.search(replace(self.request, result_limit=10))
        ids = [c["refs"][0]["id"] for c in result["value"]["candidates"]]
        self.assertEqual(set(ids), self.lazy_ids)
        self.reads.clear()
        return ids

    def test_final_one_reads_only_first_canonical_body_and_resume_reads_next(self):
        expected = self.order()
        first = self.search()
        self.assertEqual(self.first(first)["refs"][0]["id"], expected[0])
        self.assertEqual({rid for rid, _ in self.reads if rid in self.lazy_ids}, {expected[0]})
        self.assertEqual(first["consumed"]["candidates"], 1)
        self.assertTrue(first["value"]["next_cursor"])
        self.reads.clear()
        second = self.app.resume(first["value"]["query_id"], first["value"]["next_cursor"])
        self.assertEqual(self.first(second)["refs"][0]["id"], expected[1])
        self.assertEqual({rid for rid, _ in self.reads if rid in self.lazy_ids}, {expected[1]})
        self.assertEqual(second["consumed"]["candidates"], 2)
        self.assertGreater(second["consumed"]["read_bytes"], first["consumed"]["read_bytes"])
        self.assertGreater(second["consumed"]["output_chars"], first["consumed"]["output_chars"])
        self.reads.clear()
        third = self.app.resume(first["value"]["query_id"], second["value"]["next_cursor"])
        self.assertEqual(self.first(third)["refs"][0]["id"], expected[2])
        self.assertEqual({rid for rid, _ in self.reads if rid in self.lazy_ids}, {expected[2]})
        self.assertIsNone(third["value"]["next_cursor"])

    def test_rejected_first_candidate_is_refilled_before_final_k(self):
        expected = self.order()
        scope = replace(self.request.scope, exclude_ids=(expected[0],))
        result = self.search(replace(self.request, scope=scope))
        self.assertEqual(self.first(result)["refs"][0]["id"], expected[1])
        self.assertEqual({rid for rid, _ in self.reads if rid in self.lazy_ids}, {expected[1]})
        self.assertEqual(result["consumed"]["candidates"], 2)
        self.assertNotIn(expected[0], str(result["value"]["candidates"]))

    def test_repeated_resume_reuses_paid_page_without_second_candidate_charge(self):
        first = self.search()
        qid, cursor = first["value"]["query_id"], first["value"]["next_cursor"]
        page = self.app.resume(qid, cursor)
        again = self.app.resume(qid, cursor)
        self.assertEqual(page["value"], again["value"])
        self.assertEqual(page["consumed"]["candidates"], again["consumed"]["candidates"])
        self.assertEqual(page["consumed"]["output_chars"], again["consumed"]["output_chars"])
        self.assertGreater(again["consumed"]["read_bytes"], page["consumed"]["read_bytes"])

    def test_cancelled_resume_does_not_read_unvisited_candidates(self):
        first = self.search()
        self.reads.clear()
        self.app.cancel(first["value"]["query_id"])
        result = self.app.resume(first["value"]["query_id"], first["value"]["next_cursor"])
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["consumed"]["candidates"], first["consumed"]["candidates"])
        self.assertEqual(self.reads, [])

    def test_candidate_budget_is_cumulative_across_pages(self):
        request = replace(self.request, budget=replace(DEFAULT_BUDGET, candidates=2))
        first = self.search(request)
        second = self.app.resume(first["value"]["query_id"], first["value"]["next_cursor"])
        self.assertEqual(first["consumed"]["candidates"], 1)
        self.assertEqual(second["consumed"]["candidates"], 2)
        self.assertIsNone(second["value"]["next_cursor"])
        self.assertEqual(len({rid for rid, _ in self.reads if rid in self.lazy_ids}), 2)

    def test_read_budget_exhausted_after_first_page_cannot_open_next_body(self):
        measured = self.search()
        request = replace(self.request, budget=replace(DEFAULT_BUDGET, read_bytes=measured["consumed"]["read_bytes"]))
        first = self.search(request)
        self.first(first)
        self.reads.clear()
        resumed = self.app.resume(first["value"]["query_id"], first["value"]["next_cursor"])
        self.assertLessEqual(resumed["consumed"]["read_bytes"], request.budget.read_bytes)
        self.assertEqual(self.reads, [])
        self.assertFalse(resumed.get("value") and resumed["value"]["candidates"])
        self.assertTrue(resumed.get("code") == "BUDGET" or any("预算" in w for w in resumed["warnings"]), resumed)

    def test_resume_retains_frozen_revision_after_real_commit_and_reindex(self):
        expected = self.order()
        first = self.search(replace(self.request, freshness="fixed"))
        next_id = expected[1]
        key = next(k for k in ("lazy.0", "lazy.1", "lazy.2") if self.fx.record_ids[k] == next_id)
        old = self.fx.ref(key)
        self.fx.revise("lazy.revised", key, title="SYNTHETIC ONLY revised after cursor",
                       body_markdown="zqxjpageunique NEW_CANONICAL_REVISION")
        self.reads.clear()
        result = self.app.resume(first["value"]["query_id"], first["value"]["next_cursor"])
        ref = self.first(result)["refs"][0]
        self.assertEqual(ref["id"], old["target_id"])
        self.assertEqual(ref["revision"], old["revision"])
        self.assertEqual(ref["sha256"], old["sha256"])
        self.assertNotIn("NEW_CANONICAL_REVISION", self.first(result)["excerpt"])

    def test_current_resume_skips_changed_fixed_candidate_without_switching_revision(self):
        expected = self.order()
        first = self.search()
        next_id = expected[1]
        key = next(k for k in ("lazy.0", "lazy.1", "lazy.2") if self.fx.record_ids[k] == next_id)
        self.fx.revise("lazy.current.changed", key, title="SYNTHETIC ONLY changed before resume")
        result = self.app.resume(first["value"]["query_id"], first["value"]["next_cursor"])
        self.assertEqual(self.first(result)["refs"][0]["id"], expected[2])
        self.assertTrue(any("更新" in warning for warning in result["warnings"]))
        receipt = result["value"]
        packet = self.app.assemble(json_value(AssembleRequest(receipt["query_id"],
            (self.first(result)["candidate_id"],), receipt["request_digest"])))
        self.assertEqual(packet["status"], "partial", packet)
        self.assertFalse(packet["value"]["complete"])

    def test_missing_owner_watermark_is_partial_even_when_fts_rows_exist(self):
        db = index.connect(self.root, create=False)
        with db:
            self.assertGreater(db.execute("SELECT COUNT(*) FROM memory_fts").fetchone()[0], 0)
            db.execute("DELETE FROM memory_index_state WHERE owner_id=?", (self.fx.owner_ids["A"],))
        db.close()
        result = self.search()
        self.assertEqual(result["status"], "partial", result)
        self.first(result)
        self.assertTrue(any("缺少 owner" in warning for warning in result["warnings"]))

    def _fault_connection(self, failure, *, after_row=False):
        connect = index.connect

        class Connection:
            def __init__(self, actual):
                self.actual = actual

            def execute(self, sql, *args):
                if "memory_fts MATCH" not in sql:
                    return self.actual.execute(sql, *args)
                if not after_row:
                    raise failure("synthetic lexical failure")
                real = self.actual.execute(sql, *args)

                def rows():
                    yield next(iter(real))
                    raise failure("synthetic lexical iterator failure")

                return rows()

            def close(self):
                return self.actual.close()

        return patch.object(index, "connect", side_effect=lambda *a, **kw: Connection(connect(*a, **kw)))

    def test_sqlite_and_oserror_lexical_failures_preserve_completed_identity(self):
        ref = from_legacy(self.fx.ref("lazy.0"))[0]
        request = replace(self.request, scope=replace(self.request.scope, include_refs=(ref,)),
                          channels=("identity", "lexical"))
        for error in (sqlite3.OperationalError, OSError):
            with self.subTest(error=error.__name__), self._fault_connection(error):
                result = self.search(request)
                self.assertEqual(result["status"], "partial", result)
                candidate = self.first(result)
                self.assertEqual(candidate["refs"][0]["id"], ref.id)
                self.assertEqual(candidate["channels"], ["identity"])
                self.assertIsNone(candidate["hits"][0]["raw_score"])
                self.assertTrue(any("lexical" in warning for warning in result["warnings"]))
                receipt = result["value"]
                packet = self.app.assemble(json_value(AssembleRequest(receipt["query_id"],
                    (candidate["candidate_id"],), receipt["request_digest"])))
                self.assertEqual(packet["status"], "partial", packet)
                self.assertFalse(packet["value"]["complete"])
                self.assertTrue(any("lexical" in warning for warning in packet["warnings"]))

    def test_lexical_iterator_failure_keeps_its_completed_prefix(self):
        with self._fault_connection(OSError, after_row=True):
            result = self.search()
        self.assertEqual(result["status"], "partial", result)
        self.assertEqual(self.first(result)["channels"], ["lexical"])

    def test_multiple_representations_keep_individual_raw_scores_and_fixed_refs(self):
        ref = from_legacy(self.fx.ref("lazy.0"))[0]
        request = replace(self.request, question="zqxjrepresentationunique",
                          scope=replace(self.request.scope, include_refs=(ref,)),
                          channels=("identity", "lexical"))
        result = self.search(request)
        candidate = self.first(result)
        identity = [h for h in candidate["hits"] if h["channel"] == "identity"]
        lexical = [h for h in candidate["hits"] if h["channel"] == "lexical"]
        self.assertEqual(len(identity), 1)
        self.assertIsNone(identity[0]["raw_score"])
        self.assertEqual(len(lexical), 2, candidate)
        self.assertNotEqual(lexical[0]["raw_score"], lexical[1]["raw_score"])
        expected = {self.fx.record_ids["representation.problem"], self.fx.record_ids["representation.result"]}
        actual = {r["id"] for h in lexical for r in h["representation_refs"]}
        self.assertEqual(actual, expected)
        self.assertEqual({r["kind"] for h in lexical for r in h["representation_refs"]}, {"representation"})
        for hit in lexical:
            source = hit["representation_refs"][0]
            key = next(k for k in ("representation.problem", "representation.result") if self.fx.record_ids[k] == source["id"])
            self.assertEqual(source["sha256"], self.fx.ref(key)["sha256"])
            self.assertEqual(hit["provider_version"], index.PROJECTION_VERSION)
            self.assertTrue(hit["matched_text"])
            self.assertIn(hit["matched_text"], self.fx.records[key]["payload"]["text"])
        self.assertEqual(result["consumed"]["output_chars"], len(candidate["excerpt"]) +
                         sum(len(hit["matched_text"] or "") for hit in candidate["hits"]))
        # Two representations remain one lexical vote in RRF, while identity is
        # an independent vote. Diagnostics must never inflate the fused score.
        self.assertAlmostEqual(candidate["score"], 2 / 61)

    def test_representations_do_not_starve_distinct_record_window(self):
        # Both existing representations match this clue. Add the same clue to
        # another canonical record and restrict the window to two records.
        self.fx.revise('lazy.revised', 'lazy.1', body_markdown='zqxjrepresentationunique')
        result = self.search(replace(self.request, question='zqxjrepresentationunique', result_limit=2,
                                     budget=replace(DEFAULT_BUDGET, candidates=2)))
        self.assertEqual({c['refs'][0]['id'] for c in result['value']['candidates']},
                         {self.fx.record_ids['lazy.0'], self.fx.record_ids['lazy.1']})

    def test_missing_dense_model_keeps_lexical_and_reports_degradation(self):
        with patch('socket.create_connection', side_effect=AssertionError('unexpected network')):
            result = self.search(replace(self.request, channels=('lexical', 'dense')))
        self.assertEqual(result['status'], 'partial', result)
        self.assertEqual(self.first(result)['channels'], ['lexical'])
        self.assertTrue(any('dense' in warning for warning in result['warnings']))
        self.assertEqual(result['consumed']['model_calls'], 0)

    def test_old_projection_watermark_is_reported_until_rebuild(self):
        with closing(index.connect(self.root)) as db:
            db.execute("UPDATE memory_index_state SET projection_version='old-projection'")
            db.commit()
        result = self.search()
        self.assertEqual(result['status'], 'partial', result)
        self.assertTrue(any('水位' in w for w in result['warnings']))

    def test_formal_representation_fragment_is_null_without_claim_approval(self):
        record = self.fx.records["A.event"]
        claim = next(c for c in record["payload"]["claims"] if c["claim_id"] == self.fx.claims["accepted"])
        unreviewed = next(c["statement"] for c in record["payload"]["claims"] if c["claim_id"] == self.fx.claims["unreviewed"])
        target = self.fx.ref("A.event", "derived_from")
        draft = {"schema_version": 3, "owner_id": self.fx.owner_ids["A"], "kind": "representation",
                 "title": "SYNTHETIC ONLY formal diagnostic", "body_markdown": "", "keywords": [],
                 "sources": [target], "provenance_gap": None, "record_reason": "SYNTHETIC ONLY 未批准片段边界",
                 "discovery": "workspace_summary", "sensitivity": "internal",
                 "payload": {"target": target, "slot": "problem", "text": "qzxformalunreviewedtext " + unreviewed, "boundary_refs": []}}
        self.fx.commit_draft("representation.formal", draft)
        ref = FixedRef("claim", claim["claim_id"], None, memory_contracts.canonical_hash(claim), None)
        request = replace(self.request, question="qzxformalunreviewedtext", purpose="formal", applicability=SCOPE,
                          scope=replace(self.request.scope, include_refs=(ref,)), channels=("identity", "lexical"))
        result = self.search(request)
        candidate = self.first(result)
        representation_hits = [h for h in candidate["hits"] if h["channel"] == "lexical"]
        self.assertEqual(len(representation_hits), 1)
        self.assertIsNone(representation_hits[0]["matched_text"])
        self.assertNotIn(unreviewed, json.dumps(result, ensure_ascii=False))
        self.assertTrue(any("matched_text" in warning for warning in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
