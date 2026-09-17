"""E01–E10: real immutable storage in isolated synthetic workspaces.

Passing these assertions establishes software behavior, not scientific validity
of any real claim. All review actors and source texts are explicitly synthetic.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import test_memory_store as fixture
from test_memory_contracts import examples
from memory import contracts, owners
from memory.errors import MemoryError
from memory.evidence_adapter import EvidenceAdapter, formal_projection
from memory.impact import reverse_dependencies, question_resolution_validity


class MemoryEvidenceTests(unittest.TestCase):
    def test_v4_claim_containers_keep_review_and_source_boundaries(self):
        """新层级保存 claim 后仍需独立复核，不能因类别变更绕过正式准入。"""
        from memory.lineage import project
        for kind in ("narrative", "overview"):
            cid = "CLM-V4-" + kind.upper()
            value = self.value([self.claim(cid)])
            common = dict(question="合成范围", claims=value["payload"]["claims"], process_refs=[],
                          technical_refs=[], experience_refs=[], limitations=["SYNTHETIC ONLY"])
            payload = dict(common, **(
                dict(stages=[dict(situation="合成情境", action="检查", reason="回归", outcome="记录", evidence_refs=[])])
                if kind == "narrative" else dict(methods=["检查"], results=["仅合成"], current_stage="回归", open_questions=[])))
            value.update(kind=kind, schema_version=4, payload=payload)
            record = self.save(value)
            adapter = EvidenceAdapter(self.service)
            self.assertIn(cid, adapter.claims)
            self.assertEqual(adapter.formal_projection([record["record_id"]], "synthetic:A")["claims"], [])
            self.review(cid)
            approved = EvidenceAdapter(self.service).formal_projection([record["record_id"]], "synthetic:A")
            self.assertEqual([claim["claim_id"] for claim in approved["claims"]], [cid])
            self.assertEqual(project(self.service, [record["record_id"]])["source_count"], 1)

    def setUp(self):
        self.fx = fixture.MemoryStoreTests()
        self.fx.setUp()
        self.root, self.service = self.fx.root, self.fx.service
        self.source = self.root / "synthetic-source.txt"
        self.source.write_text("SYNTHETIC ONLY source A\n", encoding="utf-8")
        (self.root / "retrieval").mkdir(exist_ok=True)
        (self.root / "retrieval/sources.json").write_text(json.dumps({"schema_version": 1, "sources": [
            {"source_id": "SRC-SYN", "path": "synthetic-source.txt", "enabled": True, "sensitivity": "internal"}]}), encoding="utf-8")

    def tearDown(self):
        self.fx.tearDown()

    def test_G04_association_endpoint_acceptance_does_not_grant_formal_support(self):
        left = self.save(self.value([self.claim("CLM-LINK-LEFT")]))
        right = self.save(self.value([self.claim("CLM-LINK-RIGHT")]))
        self.review("CLM-LINK-LEFT")
        self.review("CLM-LINK-RIGHT")
        association = self.value([])
        association.update(kind="association", payload=examples()["association"])
        association["payload"].update({"from": self.record_ref(left, "analogous_to"),
            "to": self.record_ref(right, "analogous_to"), "basis_refs": [self.record_ref(left, "background")]})
        saved = self.save(association)
        adapter = EvidenceAdapter(self.service)
        projected = adapter.formal_projection([saved["record_id"]], "synthetic:A")
        self.assertEqual(projected["claims"], [])
        self.assertEqual(projected["text"], "")
        self.assertEqual(projected["rejected"][0]["errors"][0]["code"], "EVIDENCE_INELIGIBLE")
        # The valid endpoint claims remain available when explicitly requested;
        # the navigation rejection must not retract their independent evidence.
        explicit = adapter.formal_projection(["CLM-LINK-LEFT", "CLM-LINK-RIGHT"], "synthetic:A")
        self.assertEqual({item["claim_id"] for item in explicit["claims"]}, {"CLM-LINK-LEFT", "CLM-LINK-RIGHT"})

    def test_record_ref_hash_agrees_across_commit_read_formal_and_history(self):
        """A full-record pin remains readable without weakening stale checks."""
        from memory import packets
        from memory.lineage import project
        original = self.save(self.value([self.claim("CLM-HASH-ORIGINAL")]))
        self.review("CLM-HASH-ORIGINAL")
        fixed = {**self.record_ref(original, "input"), "sha256": original["record_hash"]}
        self.assertNotEqual(original["record_hash"], original["content_hash"])
        draft = self.value([self.claim("CLM-HASH-PIN", [fixed])])
        draft["sources"] = [fixed]
        derived = self.save(draft)
        # Before this regression fix the save succeeded, but inspect denied
        # this same reference because the access adapter used content_hash.
        self.assertEqual(self.service.inspect("RES-TEST", record_id=derived["record_id"])["record"], derived)
        self.review("CLM-HASH-PIN")
        self.assertTrue(EvidenceAdapter(self.service).claim_state("CLM-HASH-PIN")["effective_validity"])
        packet = packets.expand(self.service, [fixed], {"owner_id": "RES-TEST"}, 16000)
        # Packet presentation uses platform line endings; this check concerns
        # the readable fixed revision, while storage equality above is exact.
        for line in original["body_markdown"].splitlines():
            self.assertIn(line, packet["context_text"])
        self.assertEqual(project(self.service, [derived["record_id"]])["source_count"], 1)
        # The dedup/review hash must be rejected, not accepted as a second
        # interchangeable fingerprint format that could mask caller mistakes.
        wrong = deepcopy(draft)
        wrong["sources"][0]["sha256"] = original["content_hash"]
        before = fixture.snapshot_files(self.root)
        self.assert_code("STALE_BASIS", lambda: self.save(wrong))
        self.assertEqual(before, fixture.snapshot_files(self.root))
        # Pinning a future revision in the same transaction must not bypass
        # fingerprint validation in the pending-record resolution branch.
        updated_draft = self.value([self.claim("CLM-HASH-ORIGINAL")])
        updated_draft["body_markdown"] += "\nSYNTHETIC proposed batch update"
        head = self.service.inspect("RES-TEST")["head"]["commit_id"]
        batch = fixture.request(updated_draft, head=head, rid=original["record_id"], revision=1)
        future_draft = self.value([])
        future_draft["sources"] = [{**fixed, "revision": 2, "sha256": "0" * 64}]
        batch["operations"].append({"op": "put_record", "client_key": "future-dependent", "draft": future_draft})
        self.assert_code("STALE_BASIS", lambda: self.service.commit(batch))
        self.assertEqual(before, fixture.snapshot_files(self.root))
        revised = self.value([])
        revised["body_markdown"] += "\nSYNTHETIC revised source context"
        self.save(revised, original)
        self.assertFalse(EvidenceAdapter(self.service).claim_state("CLM-HASH-PIN")["effective_validity"])
        # Historical navigation still follows r1's actual complete hash.
        self.assertEqual(self.service.inspect("RES-TEST", record_id=derived["record_id"])["record"], derived)
        registry = self.root / "retrieval/sources.json"
        value = json.loads(registry.read_text(encoding="utf-8"))
        value["sources"][0]["enabled"] = False
        registry.write_text(json.dumps(value), encoding="utf-8")
        self.assert_code("ACCESS_DENIED", lambda: self.service.inspect("RES-TEST", record_id=derived["record_id"]))

    def test_fixed_historical_provenance_cannot_borrow_clean_current_sources(self):
        from memory.lineage import project
        original = self.save(self.value([]))
        derived_draft = self.value([])
        derived_draft["sources"] = [self.record_ref(original, "background")]
        derived = self.save(derived_draft)
        clean = self.value([])
        clean["sources"] = []
        clean["provenance_gap"] = "Synthetic current revision has no acquired source"
        updated = self.save(clean, original)
        # Even before revocation, lineage must walk the pinned old version,
        # which still names the actual registered original.
        self.assertEqual(project(self.service, [derived["record_id"]])["source_count"], 1)
        registry = self.root / "retrieval/sources.json"
        data = json.loads(registry.read_text(encoding="utf-8"))
        data["sources"][0]["enabled"] = False
        registry.write_text(json.dumps(data), encoding="utf-8")
        before = fixture.snapshot_files(self.root)
        adapter = EvidenceAdapter(self.service)
        self.assertEqual(adapter.access_errors(updated["record_id"]), [])
        self.assertTrue(adapter.access_errors(derived["record_id"]))
        self.assertTrue(adapter.access_errors(original["record_id"], revision=1))
        self.assert_code("ACCESS_DENIED", lambda: self.service.inspect("RES-TEST", record_id=original["record_id"], revision=1))
        self.assert_code("ACCESS_DENIED", lambda: self.service.inspect("RES-TEST", record_id=derived["record_id"]))
        self.assertEqual(project(self.service, [derived["record_id"]])["source_count"], 0)
        self.assertEqual(before, fixture.snapshot_files(self.root))

    def test_unchanged_claim_hash_preserves_parent_source_permission_union(self):
        from memory.lineage import project
        draft = self.value([self.claim("CLM-PARENT-PROVENANCE", [])])
        original = self.save(draft)
        fixed = self.claim_ref("CLM-PARENT-PROVENANCE", "background")
        draft["sources"] = []
        draft["provenance_gap"] = "Synthetic missing parent source in current revision"
        self.save(draft, original)
        self.assertEqual(project(self.service, [fixed["target_id"]])["source_count"], 1)
        registry = self.root / "retrieval/sources.json"
        data = json.loads(registry.read_text(encoding="utf-8"))
        data["sources"][0]["enabled"] = False
        registry.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(EvidenceAdapter(self.service).access_errors(fixed))
        self.assertEqual(project(self.service, [fixed["target_id"]])["source_count"], 0)
        native = self.root / "research/中文 专题/research.json"
        metadata = json.loads(native.read_text(encoding="utf-8"))
        metadata["sensitivity"] = "restricted"
        native.write_text(json.dumps(metadata), encoding="utf-8")
        adapter = EvidenceAdapter(self.service)
        from unittest.mock import patch
        with patch.object(self.service.store, "read_record", side_effect=AssertionError("restricted history was opened")):
            self.assert_code("ACCESS_DENIED", lambda: adapter.access_record(original["record_id"], 1))

    def file_ref(self, relation="supports"):
        return {"target_kind": "file", "target_id": "SRC-SYN", "revision": None,
                "sha256": hashlib.sha256(self.source.read_bytes()).hexdigest(), "locator": "lines:1-1", "relation": relation}

    def claim(self, cid, refs=None):
        return {"claim_id": cid, "statement": "SYNTHETIC ONLY " + cid, "kind": "calculation", "scope": "synthetic:A",
                "evidence_refs": deepcopy(refs if refs is not None else [self.file_ref()])}

    def value(self, claims, owner="RES-TEST"):
        result = fixture.draft(owner)
        result["sources"] = [self.file_ref("background")]
        result["provenance_gap"] = None
        result["payload"]["claims"] = claims
        return result

    def save(self, draft, record=None):
        snapshot = self.service.inspect(draft["owner_id"])
        request = fixture.request(draft, head=(snapshot["head"] or {}).get("commit_id"),
                                  rid=record["record_id"] if record else None, revision=record["revision"] if record else None)
        receipt = self.service.commit(request)
        return self.service.inspect(draft["owner_id"], record_id=receipt["record_results"][0]["record_id"])["record"]

    def review(self, cid, state="accepted", **changes):
        adapter = EvidenceAdapter(self.service)
        value = adapter.resolve_claim(cid)
        owner = value["owner_id"]
        head = self.service.inspect(owner)["head"]
        request = {"schema_version": 1, "request_id": str(uuid.uuid4()), "owner_id": owner,
                   "expected_head": head["commit_id"] if head else None, "actor": {"kind": "workflow", "id": "synthetic-evidence-test"},
                   "target_claim_id": cid, "state": state, "reason": "SYNTHETIC ONLY regression review",
                   "scope": "synthetic:A" if state == "accepted" else None, "evidence_refs": [self.file_ref()] if state == "accepted" else []}
        request.update(changes)
        return self.service.review(request)

    def claim_ref(self, cid, relation="supports"):
        resolved = EvidenceAdapter(self.service).resolve_claim(cid)
        return {"target_kind": "claim", "target_id": cid, "revision": None, "sha256": resolved["sha256"],
                "locator": "claim:" + cid, "relation": relation}

    @staticmethod
    def record_ref(record, relation="references"):
        return {"target_kind": "record", "target_id": record["record_id"], "revision": record["revision"],
                "sha256": None, "locator": "payload", "relation": relation}

    def assert_code(self, code, call):
        with self.assertRaises(MemoryError) as caught:
            call()
        self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_E01_review_requires_scope_evidence_and_is_per_claim(self):
        record = self.save(self.value([self.claim("CLM-A"), self.claim("CLM-B")]))
        before = fixture.snapshot_files(self.root)
        self.assert_code("EVIDENCE_INELIGIBLE", lambda: self.review("CLM-A", scope=None))
        self.assert_code("EVIDENCE_INELIGIBLE", lambda: self.review("CLM-A", evidence_refs=[]))
        self.assertEqual(before, fixture.snapshot_files(self.root))
        self.review("CLM-A")
        adapter = EvidenceAdapter(self.service)
        review = adapter.reviews["CLM-A"]["payload"]
        self.assertEqual(review["target_content_hash"], record["content_hash"])
        self.assertEqual(review["reviewer"]["id"], "synthetic-evidence-test")
        self.assertEqual(review["scope"], "synthetic:A")
        self.assertTrue(review["evidence_refs"])
        self.assertTrue(adapter.claim_state("CLM-A")["effective_validity"])
        self.assertEqual(adapter.claim_state("CLM-B")["review_state"], "not-reviewed")
        # Detail uses the real stored review but does not claim a fresh full
        # evidence validation merely because a record was opened successfully.
        from types import SimpleNamespace
        from material_query.evidence_navigation import detail
        result = detail(SimpleNamespace(root=self.root, materials=SimpleNamespace(access_owner_ids=None)),
                        {'id':record['record_id']})
        displayed = {item['claim_id']:item for item in result['claim_reviews']}
        self.assertEqual(displayed['CLM-A']['state'], 'accepted')
        self.assertTrue(displayed['CLM-A']['content_matches'])
        self.assertEqual(displayed['CLM-B']['state'], 'not-reviewed')
        self.assertEqual(displayed['CLM-A']['evidence_validity'], 'not_rechecked')
        self.assertIn(record['body_markdown'], result['content_markdown'])
        self.assertIn('SYNTHETIC ONLY CLM-A', result['structured_content_markdown'])

    def test_E02_ordinary_commit_cannot_forge_review(self):
        self.save(self.value([self.claim("CLM-A")]))
        before = fixture.snapshot_files(self.root)
        forged = self.value([dict(self.claim("CLM-B"), review={"state": "accepted"})])
        self.assert_code("INVALID_SCHEMA", lambda: self.save(forged))
        forged = self.value([])
        forged.update(kind="review", payload=examples()["review"])
        self.assert_code("INVALID_SCHEMA", lambda: self.save(forged))
        self.assertEqual(before, fixture.snapshot_files(self.root))

    def test_E03_unrelated_progress_preserves_accepted_content(self):
        original = self.save(self.value([self.claim("CLM-A")]))
        self.review("CLM-A")
        for kind in ("goal", "checkpoint", "policy", "experience"):
            value = self.value([])
            value.update(kind=kind, payload=examples()[kind])
            if kind == "checkpoint":
                value["payload"]["goal_ref"] = self.record_ref(goal)
            result = self.save(value)
            if kind == "goal":
                goal = result
        current = EvidenceAdapter(self.service)
        self.assertEqual(current.claims["CLM-A"][1]["content_hash"], original["content_hash"])
        self.assertTrue(current.claim_state("CLM-A")["effective_validity"])

    def test_E04_statement_boundary_source_changes_invalidate_bindings(self):
        value = self.value([self.claim("CLM-A")])
        record = self.save(value)
        self.review("CLM-A")
        first_review = EvidenceAdapter(self.service).reviews["CLM-A"]
        for field in ("statement", "boundary"):
            if field == "statement":
                value["payload"]["claims"][0]["statement"] += " revised"
            else:
                value["payload"]["applicable"] = ["SYNTHETIC ONLY narrower boundary"]
            record = self.save(value, record)
            state = EvidenceAdapter(self.service).claim_state("CLM-A")
            self.assertFalse(state["effective_validity"])
            self.assertTrue(any(item["code"] == "STALE_BASIS" for item in state["errors"]))
            self.review("CLM-A")
        self.source.write_text("SYNTHETIC ONLY changed original", encoding="utf-8")
        state = EvidenceAdapter(self.service).claim_state("CLM-A")
        self.assertFalse(state["effective_validity"])
        self.assertTrue(any(item["target_id"] == "SRC-SYN" for item in state["errors"]))
        old = self.service.inspect("RES-TEST", 1, record_id=first_review["record_id"])["record"]
        self.assertEqual(old, first_review)

    def test_E05_cross_owner_retraction_and_maps_ignore_stale_projection(self):
        for project in ("PRJ-SOURCE", "PRJ-OTHER"):
            path = self.root / "projects" / project / "project.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"schema_version": 1, "project_id": project, "title": "SYNTHETIC ONLY"}), encoding="utf-8")
        native = self.root / "research/中文 专题/research.json"
        metadata = json.loads(native.read_text(encoding="utf-8"))
        metadata["project_id"] = "PRJ-SOURCE"
        native.write_text(json.dumps(metadata), encoding="utf-8")
        source = self.save(self.value([self.claim("CLM-A")]))
        self.review("CLM-A")
        report = self.root / "reports/sources/synthetic.md"
        report.parent.mkdir(parents=True)
        report.write_text("SYNTHETIC ONLY report", encoding="utf-8")
        report.with_name("synthetic.md.evidence.json").write_text(json.dumps({"schema_version": 1, "evidence_id": "EVD-REPORT",
            "document_path": "reports/sources/synthetic.md", "claims": []}), encoding="utf-8")
        downstream = self.save(self.value([self.claim("CLM-B", [self.claim_ref("CLM-A")])], "PRJ-OTHER"))
        self.review("CLM-B")
        self.save(self.value([self.claim("CLM-C", [self.claim_ref("CLM-B")])], "EVD-REPORT"))
        self.review("CLM-C")
        map_value = self.value([], "PRJ-OTHER")
        map_value.update(kind="map", payload=examples()["map"])
        map_value["payload"]["result_refs"] = [self.record_ref(downstream, "derived_from")]
        navigation = self.save(map_value)
        cached = formal_projection(self.root, ["CLM-C"], "synthetic:A")
        self.assertTrue(cached["claims"])
        self.review("CLM-A", "retracted")
        fresh = formal_projection(self.root, ["CLM-A", "CLM-B", "CLM-C", navigation["record_id"]], "synthetic:A")
        self.assertFalse(fresh["claims"])
        c_failure = next(item for item in fresh["rejected"] if item["canonical_id"] == "CLM-C")
        self.assertTrue(any(item["path"] == ["CLM-A", "CLM-B", "CLM-C"] for item in c_failure["errors"]))
        self.assertEqual(self.service.inspect("RES-TEST", 1, record_id=source["record_id"])["record"], source)

    def test_E06_support_and_navigation_have_distinct_propagation(self):
        self.save(self.value([self.claim("CLM-A")]))
        self.review("CLM-A")
        for relation in ("supports", "input", "background", "contradicts", "analogous_to"):
            refs = [self.file_ref(), self.claim_ref("CLM-A", relation)]
            self.save(self.value([self.claim("CLM-" + relation, refs)]))
            self.review("CLM-" + relation)
        self.review("CLM-A", "retracted")
        adapter = EvidenceAdapter(self.service)
        for relation in ("supports", "input", "background", "contradicts", "analogous_to"):
            state = adapter.claim_state("CLM-" + relation)
            self.assertEqual(state["effective_validity"], relation not in {"supports", "input"})
            self.assertEqual(state["review_state"], "accepted")
        affected = {item["canonical_id"]: item for item in reverse_dependencies(self.root, ["CLM-A"])["affected"]}
        self.assertTrue(affected["CLM-supports"]["formal_dependency"])
        self.assertFalse(affected["CLM-analogous_to"]["formal_dependency"])

    def test_E07_missing_cycles_and_diamond_are_bounded_and_deduplicated(self):
        self.save(self.value([self.claim("CLM-A")]))
        self.review("CLM-A")
        for cid in ("CLM-B", "CLM-C"):
            self.save(self.value([self.claim(cid, [self.claim_ref("CLM-A")])]))
            self.review(cid)
        self.save(self.value([self.claim("CLM-D", [self.claim_ref("CLM-B"), self.claim_ref("CLM-C")])]))
        self.review("CLM-D")
        self.review("CLM-A", "retracted")
        failures = EvidenceAdapter(self.service).claim_state("CLM-D")["errors"]
        self.assertEqual(sum(item["target_id"] == "CLM-A" and "retracted" in item["message"] for item in failures), 1)
        # Isolated read-graph corruption fixtures exercise cycles/missing refs;
        # production commits already reject new unsupported references.
        adapter = EvidenceAdapter(self.service)
        a, ar = adapter.claims["CLM-A"]
        _d, dr = adapter.claims["CLM-D"]
        # Fixed record revisions can express a cycle without attempting an
        # impossible mutually recursive SHA-256 definition for claim values.
        ar["sources"] = [self.record_ref(dr, "supports")]
        dr["sources"] = [self.record_ref(ar, "supports")]
        failures = adapter._analyze(ar["record_id"], "synthetic:A")
        self.assertTrue(any("cycle" in item["message"] for item in failures))
        a["evidence_refs"] = [dict(self.file_ref(), target_id="SRC-MISSING")]
        failures = adapter._analyze("CLM-A", "synthetic:A")
        self.assertTrue(any(item["code"] == "UNRESOLVED_REFERENCE" for item in failures))

    def test_E08_replacement_history_and_reacceptance(self):
        self.save(self.value([self.claim("CLM-A"), self.claim("CLM-B")]))
        self.review("CLM-A")
        self.assert_code("EVIDENCE_INELIGIBLE", lambda: self.review("CLM-A", "superseded", replacement_claim_id="CLM-A"))
        self.assert_code("UNRESOLVED_REFERENCE", lambda: self.review("CLM-A", "superseded", replacement_claim_id="CLM-MISSING"))
        self.review("CLM-A", "superseded", replacement_claim_id="CLM-B")
        self.review("CLM-B", "retracted")
        self.assertFalse(EvidenceAdapter(self.service).claim_state("CLM-A")["effective_validity"])
        extra = self.root / "synthetic-new-evidence.txt"
        extra.write_text("SYNTHETIC ONLY independent new evidence", encoding="utf-8")
        registry_path = self.root / "retrieval/sources.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["sources"].append({"source_id": "SRC-NEW", "path": extra.name, "enabled": True, "sensitivity": "internal"})
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        new_basis = dict(self.file_ref(), target_id="SRC-NEW", sha256=hashlib.sha256(extra.read_bytes()).hexdigest())
        self.review("CLM-A", "accepted", evidence_refs=[new_basis])
        review = EvidenceAdapter(self.service).reviews["CLM-A"]
        states = [self.service.inspect("RES-TEST", version, record_id=review["record_id"])["record"]["payload"]["state"]
                  for version in range(1, review["revision"] + 1)]
        self.assertEqual(states, ["accepted", "superseded", "accepted"])
        self.assertEqual(review["payload"]["evidence_refs"], [new_basis])
        self.assertTrue(EvidenceAdapter(self.service).claim_state("CLM-A")["effective_validity"])

    def test_E09_mixed_claims_and_explicit_formal_scope(self):
        record = self.save(self.value([self.claim("CLM-A"), self.claim("CLM-B"), self.claim("CLM-C")]))
        self.review("CLM-A")
        self.review("CLM-C", "disputed")
        output = formal_projection(self.root, [record["record_id"]], "synthetic:A")
        self.assertEqual([item["claim_id"] for item in output["claims"]], ["CLM-A"])
        self.assertNotIn("CLM-B", output["text"])
        self.assertFalse(formal_projection(self.root, [record["record_id"]], "synthetic:B")["text"])

    def test_E10_question_resolution_invalidation_keeps_history(self):
        self.save(self.value([self.claim("CLM-A")]))
        self.review("CLM-A")
        value = self.value([])
        value.update(kind="question", payload=examples()["question"])
        value["payload"].update(status="resolved", resolution_refs=[self.claim_ref("CLM-A")])
        question = self.save(value)
        self.assertFalse(question_resolution_validity(self.root, question["record_id"])["resolution_needs_revalidation"])
        self.review("CLM-A", "retracted")
        state = question_resolution_validity(self.root, question["record_id"])
        self.assertEqual(state["status"], "resolved")
        self.assertTrue(state["resolution_needs_revalidation"])
        self.assertEqual(self.service.inspect("RES-TEST", 1, record_id=question["record_id"])["record"], question)

    def test_E05_E08_legacy_review_and_run_seal_are_preserved(self):
        import test_evidence as old_fixture
        import evidence
        from memory.service import MemoryService
        old = old_fixture.EvidenceTests()
        old.setUp()
        try:
            path = old.root / "research/evidence-case/research.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"schema_version": 1, "research_id": "RES-MEM", "title": "SYNTHETIC ONLY"}), encoding="utf-8")
            service = MemoryService(old.root)
            graph = evidence.EvidenceGraph(old.root)
            reference = {"target_kind": "claim", "target_id": "CLM-BASE", "revision": None,
                         "sha256": graph.nodes["CLM-BASE"]["fingerprint"], "locator": "claim:CLM-BASE", "relation": "supports"}
            native_before = old.run_path.read_bytes()
            value = fixture.draft("RES-MEM")
            value.update(sources=[reference], provenance_gap=None)
            value["payload"]["claims"] = [{"claim_id": "CLM-MEM", "statement": "SYNTHETIC ONLY reused legacy result",
                                            "scope": "bench:A", "kind": "inference", "evidence_refs": [reference]}]
            receipt = service.commit(fixture.request(value))
            req = {"schema_version": 1, "request_id": str(uuid.uuid4()), "owner_id": "RES-MEM",
                   "expected_head": receipt["commit_id"], "target_claim_id": "CLM-MEM", "state": "accepted",
                   "actor": {"kind": "workflow", "id": "synthetic-test"}, "reason": "SYNTHETIC ONLY",
                   "scope": "bench:A", "evidence_refs": [reference]}
            service.review(req)
            self.assertEqual(old.run_path.read_bytes(), native_before)
            self.assertFalse(evidence.EvidenceGraph(old.root).claim_errors("CLM-BASE", "bench:A"))
            self.assertTrue(formal_projection(old.root, ["CLM-MEM"], "bench:A")["claims"])
            old_request = dict(req, request_id=str(uuid.uuid4()), owner_id="RUN-BASE", expected_head=None,
                               target_claim_id="CLM-BASE", state="retracted", scope=None, evidence_refs=[])
            service.review(old_request)
            result = formal_projection(old.root, ["CLM-MEM"], "bench:A")
            self.assertFalse(result["claims"])
            self.assertTrue(any(error["path"] == ["CLM-BASE", "CLM-MEM"] for item in result["rejected"] for error in item["errors"]))
            native = json.loads(old.run_path.read_text(encoding="utf-8"))
            self.assertEqual(native["status"], "succeeded")
            self.assertEqual(native["claims"][0]["review"]["status"], "retracted")
            self.assertTrue(native["claims"][0]["review_history"])
            checks = EvidenceAdapter(service).basis_checks
            legacy_check = next(check for check in checks if check.get("path") == "runs/base/run.json")
            self.assertEqual(legacy_check["kind"], "legacy_file")
            # A later review withdrawal/restoration is visible to prepublish
            # even though legacy.fingerprint deliberately excludes reviews.
            native["claims"][0]["review"]["reason"] += " changed after prepare"
            old.run_path.write_text(json.dumps(native), encoding="utf-8")
            self.assert_code("STALE_BASIS", lambda: service._recheck([legacy_check]))
            registry_path = old.root / "retrieval/sources.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry.setdefault("sources", []).append({"source_id": "SRC-DISABLED-LEGACY", "path": old.source.relative_to(old.root).as_posix(),
                                                       "enabled": False, "sensitivity": "internal"})
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            access = EvidenceAdapter(service).access_errors("CLM-MEM")
            self.assertTrue(any(error["code"] == "ACCESS_DENIED" for error in access))
        finally:
            old.tearDown()

    def test_source_permissions_propagate_through_memory_source_navigation(self):
        source_value = self.value([])
        source_value.update(kind="source", payload=examples()["source"])
        source_value["payload"]["source_ref"] = self.file_ref("background")
        source = self.save(source_value)
        value = self.value([self.claim("CLM-A")])
        value["sources"] = [self.record_ref(source, "background")]
        self.save(value)
        self.assertFalse(EvidenceAdapter(self.service).access_errors("CLM-A"))
        registry_path = self.root / "retrieval/sources.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["sources"][0]["enabled"] = False
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        errors = EvidenceAdapter(self.service).access_errors("CLM-A")
        self.assertTrue(any(error["code"] == "ACCESS_DENIED" and source["record_id"] in error["path"] for error in errors))
        self.assertFalse(formal_projection(self.root, ["CLM-A"], "synthetic:A")["text"])


if __name__ == "__main__":
    unittest.main()
