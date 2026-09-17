"""Backend contract for the single workspace-wide settings authority.

All cases use an empty temporary root.  They deliberately exercise only the
settings file, never create owners, materials, indexes, or reading sessions.
"""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from memory.errors import MemoryError
import workspace_settings


class WorkspaceSettingsTests(unittest.TestCase):
    def test_three_modes_legacy_read_is_byte_preserving_and_writes_are_strict(self):
        before = self.read()
        self.assertEqual(before['settings']['reading']['strategy'], 'standard')
        self.assertEqual(before['settings']['reading']['association'], {'enabled': True, 'max_rounds': 3})
        legacy = deepcopy(before['settings'])
        del legacy['reading']['strategy']
        del legacy['reading']['association']
        raw = json.dumps({'schema_version': 1, 'settings': legacy}).encode()
        path = self.root / 'workspace-settings.json'
        path.write_bytes(raw)
        loaded = self.read()
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(loaded['revision'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(loaded['settings'], before['settings'])
        self.assert_error('INVALID_ARGUMENT', lambda: self.update(loaded, legacy))
        for strategy in ('quick', 'associative', 'standard'):
            loaded['settings']['reading']['strategy'] = strategy
            loaded = self.update(loaded)
            self.assertEqual(self.read()['settings']['reading']['strategy'], strategy)
        for association in ({'enabled': 1, 'max_rounds': 3}, {'enabled': True, 'max_rounds': 0},
                            {'enabled': True, 'max_rounds': 21}, {'enabled': True, 'max_rounds': True}):
            bad = deepcopy(loaded['settings'])
            bad['reading']['association'] = association
            self.assert_error('INVALID_ARGUMENT', lambda: self.update(loaded, bad))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "empty workspace"
        self.root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def read(self):
        return workspace_settings.read(self.root)

    def update(self, snapshot, settings=None):
        return workspace_settings.update(self.root, {"expected_revision": snapshot["revision"],
            "settings": deepcopy(settings if settings is not None else snapshot["settings"])})

    def assert_error(self, code, callback):
        with self.assertRaises(MemoryError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code)

    def test_missing_file_returns_complete_defaults_without_creating_any_file(self):
        value = self.read()
        self.assertEqual(value["settings"], value["defaults"])
        self.assertEqual(set(value), {"revision", "settings", "defaults", "limits"})
        self.assertEqual(value["settings"]["collaboration"]["subagents"], "auto")
        self.assertEqual(value["settings"]["materials"]["result_limit"], 20)
        self.assertEqual(value["settings"]["reading"]["result_limit"], 10)
        self.assertEqual(value["settings"]["reading"]["screening"],
                         {"regular_windows": 3, "max_windows": 4, "batch_owners": 10})
        self.assertEqual(value["settings"]["reading"]["reranking"], {
            "mode": "auto", "candidate_limit": 30, "window_tokens": 512,
            "overflow_policy": "hit_centered_per_window"})
        self.assertFalse((self.root / "workspace-settings.json").exists())
        self.assertFalse((self.root / "workspace-settings.json.lock").exists())

    def test_update_is_complete_cas_and_persists_only_authoritative_shape(self):
        before = self.read()
        changed = deepcopy(before["settings"])
        changed["collaboration"]["subagents"] = "off"
        changed["reading"]["result_limit"] = 7
        changed["reading"]["reranking"]["candidate_limit"] = 7
        saved = self.update(before, changed)
        self.assertNotEqual(saved["revision"], before["revision"])
        self.assertEqual(saved["settings"], changed)
        persisted = json.loads((self.root / "workspace-settings.json").read_text(encoding="utf-8"))
        self.assertEqual(set(persisted), {"schema_version", "settings"})
        self.assertEqual(persisted["schema_version"], 1)
        self.assertEqual(persisted["settings"], changed)
        self.assert_error("VERSION_CONFLICT", lambda: self.update(before, changed))

    def test_context_budget_migrates_legacy_disk_without_changing_custom_values(self):
        settings = self.read()['settings']
        self.assertEqual(settings['reading'].pop('context'), {'max_owners': 10, 'note_max_tokens': 6000})
        settings['reading']['budget']['output_chars'] = 4321
        settings['collaboration']['subagent_requirements'] = '保留自定义要求'
        raw = json.dumps({'schema_version': 1, 'settings': settings}).encode('utf-8')
        path = self.root / 'workspace-settings.json'
        path.write_bytes(raw)
        shown = self.read()
        expected = deepcopy(settings)
        expected['reading']['context'] = {'max_owners': 10, 'note_max_tokens': 6000}
        self.assertEqual(shown['settings'], expected)
        self.assertEqual(shown['revision'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(path.read_bytes(), raw)
        self.assert_error('INVALID_ARGUMENT', lambda: self.update(shown, settings))
        self.assertEqual(self.update(shown)['settings'], expected)

    def test_context_budget_strict_shape_bounds_and_independent_roundtrip(self):
        saved = self.read()
        for key, invalids in (('max_owners', (0, 101, True, 1.5, '10')),
                              ('note_max_tokens', (511, 50001, True, 1.5, '6000'))):
            for value in invalids:
                changed = deepcopy(saved['settings'])
                changed['reading']['context'][key] = value
                self.assert_error('INVALID_ARGUMENT', lambda: self.update(saved, changed))
        for context in ({}, {'max_owners': 10}, {'max_owners': 10, 'note_max_tokens': 6000, 'unknown': 1}):
            changed = deepcopy(saved['settings'])
            changed['reading']['context'] = context
            self.assert_error('INVALID_ARGUMENT', lambda: self.update(saved, changed))
        for context in ({'max_owners': 1, 'note_max_tokens': 512}, {'max_owners': 100, 'note_max_tokens': 50000}):
            changed = deepcopy(saved['settings'])
            changed['reading']['context'] = context
            saved = self.update(saved, changed)
            self.assertEqual(self.read()['settings'], changed)

    def test_discovery_screening_and_ce_window_settings_are_strict_and_legacy_read_is_byte_preserving(self):
        current = self.read()
        legacy = deepcopy(current['settings'])
        del legacy['reading']['screening']
        del legacy['reading']['reranking']['window_tokens']
        del legacy['reading']['reranking']['overflow_policy']
        raw = json.dumps({'schema_version': 1, 'settings': legacy}).encode('utf-8')
        path = self.root / 'workspace-settings.json'
        path.write_bytes(raw)
        shown = self.read()
        self.assertEqual(shown['settings'], current['settings'])
        self.assertEqual(shown['revision'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(path.read_bytes(), raw)
        # 写入继续要求完整新快照，旧客户端不能把新增策略悄悄抹掉。
        self.assert_error('INVALID_ARGUMENT', lambda: self.update(shown, legacy))

        valid = shown
        for screening in (
            {'regular_windows': 0, 'max_windows': 4, 'batch_owners': 10},
            {'regular_windows': 5, 'max_windows': 4, 'batch_owners': 10},
            {'regular_windows': 3, 'max_windows': 5, 'batch_owners': 10},
            {'regular_windows': 3, 'max_windows': 4, 'batch_owners': 0},
            {'regular_windows': 3, 'max_windows': 4, 'batch_owners': 101},
        ):
            changed = deepcopy(valid['settings'])
            changed['reading']['screening'] = screening
            self.assert_error('INVALID_ARGUMENT', lambda: self.update(valid, changed))
        for tokens in (63, 513, True, 512.0, '512'):
            changed = deepcopy(valid['settings'])
            changed['reading']['reranking']['window_tokens'] = tokens
            self.assert_error('INVALID_ARGUMENT', lambda: self.update(valid, changed))
        changed = deepcopy(valid['settings'])
        changed['reading']['reranking']['overflow_policy'] = 'whole_batch_fallback'
        self.assert_error('INVALID_ARGUMENT', lambda: self.update(valid, changed))

    def test_invalid_shape_numbers_limits_and_corrupt_file_are_rejected(self):
        base = self.read()
        cases = []
        unknown = deepcopy(base["settings"]); unknown["other"] = True; cases.append(unknown)
        missing = deepcopy(base["settings"]); del missing["materials"]["budget"]; cases.append(missing)
        boolean = deepcopy(base["settings"]); boolean["materials"]["result_limit"] = True; cases.append(boolean)
        zero_wall = deepcopy(base["settings"]); zero_wall["reading"]["budget"]["wall_ms"] = 0; cases.append(zero_wall)
        beyond = deepcopy(base["settings"]); beyond["materials"]["budget"]["read_bytes"] = base["limits"]["read_bytes"] + 1; cases.append(beyond)
        inverted = deepcopy(base["settings"]); inverted["reading"]["reranking"]["candidate_limit"] = inverted["reading"]["result_limit"] - 1; cases.append(inverted)
        bad_limit = deepcopy(base["settings"]); bad_limit["materials"]["result_limit"] = 101; cases.append(bad_limit)
        for settings in cases:
            self.assert_error("INVALID_ARGUMENT", lambda settings=settings: self.update(base, settings))
        off = deepcopy(base["settings"])
        off["reading"]["reranking"].update(mode="off", candidate_limit=1)
        self.assertEqual(self.update(base, off)["settings"]["reading"]["reranking"], off["reading"]["reranking"])
        (self.root / "workspace-settings.json").write_text("{not-json", encoding="utf-8")
        self.assert_error("INVALID_ARGUMENT", self.read)

    def test_existing_lock_is_refused_without_overwrite(self):
        snapshot = self.read()
        lock = self.root / "workspace-settings.json.lock"
        lock.write_text("other process", encoding="utf-8")
        self.assert_error("LOCKED", lambda: self.update(snapshot))
        self.assertEqual(lock.read_text(encoding="utf-8"), "other process")
        self.assertFalse((self.root / "workspace-settings.json").exists())

    def test_legacy_disk_adds_only_new_default_without_changing_bytes_or_revision(self):
        legacy = self.read()['settings']
        del legacy['collaboration']['subagent_requirements']
        raw = json.dumps({'schema_version': 1, 'settings': legacy}).encode('utf-8')
        path = self.root / 'workspace-settings.json'
        path.write_bytes(raw)
        shown = self.read()
        self.assertEqual(shown['settings']['collaboration']['subagent_requirements'],
                         shown['defaults']['collaboration']['subagent_requirements'])
        self.assertEqual(shown['revision'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(path.read_bytes(), raw)
        self.assert_error('INVALID_ARGUMENT', lambda: self.update(shown, legacy))
        self.assertEqual(path.read_bytes(), raw)
        # Compatibility does not repair unrelated missing fields or unknown keys.
        for mutate in (lambda s: s['reading'].pop('budget'),
                       lambda s: s['collaboration'].update(unknown=True)):
            broken = deepcopy(legacy)
            mutate(broken)
            path.write_text(json.dumps({'schema_version': 1, 'settings': broken}), encoding='utf-8')
            self.assert_error('INVALID_ARGUMENT', self.read)

    def test_requirements_text_bounds_preservation_and_incomplete_write_rejection(self):
        saved = self.read()
        for invalid in (None, True, 123, [], '', ' \n\t ', '能' * 2001):
            changed = deepcopy(saved['settings'])
            changed['collaboration']['subagent_requirements'] = invalid
            self.assert_error('INVALID_ARGUMENT', lambda: self.update(saved, changed))
        for valid in ('能', ' \n' + '能' * 2000 + '\t ', '  高能力模型；high reasoning\n保留原文。  '):
            changed = deepcopy(saved['settings'])
            changed['collaboration']['subagent_requirements'] = valid
            saved = self.update(saved, changed)
            self.assertEqual(self.read()['settings']['collaboration']['subagent_requirements'], valid)
        before = (self.root / 'workspace-settings.json').read_bytes()
        changed = deepcopy(saved['settings'])
        del changed['collaboration']['subagent_requirements']
        self.assert_error('INVALID_ARGUMENT', lambda: self.update(saved, changed))
        self.assertEqual((self.root / 'workspace-settings.json').read_bytes(), before)

    def test_unchanged_valid_file_is_decoded_once_across_consecutive_reads(self):
        snapshot = self.read()
        self.update(snapshot)
        # The update may cache its published value; a fresh root path prevents
        # that implementation detail from satisfying the read-cache assertion.
        fresh = Path(self.temp.name) / "fresh workspace"
        fresh.mkdir()
        shutil = __import__("shutil")
        shutil.copy2(self.root / "workspace-settings.json", fresh / "workspace-settings.json")
        original = workspace_settings.json.loads
        with patch.object(workspace_settings.json, "loads", wraps=original) as loads:
            first = workspace_settings.read(fresh)
            second = workspace_settings.read(fresh)
        self.assertEqual(first, second)
        self.assertEqual(loads.call_count, 1)

    def test_returned_nested_objects_do_not_mutate_cached_settings_or_defaults(self):
        saved = self.update(self.read())
        expected = deepcopy(saved)
        saved['settings']['reading']['budget']['model_calls'] = 0
        saved['defaults']['materials']['budget']['read_bytes'] = 1
        saved['limits']['read_bytes'] = 1
        self.assertEqual(self.read(), expected)

    def test_atomic_external_edit_invalidates_cache_even_with_same_size_and_mtime(self):
        saved = self.update(self.read())
        path = self.root / 'workspace-settings.json'
        original_stat = path.stat()
        original = path.read_bytes()
        # 等长值替换并恢复 mtime，逼迫缓存检查文件身份/ctime 而非只看时间和大小。
        payload = json.loads(original)
        payload['settings']['materials']['result_limit'] = 21
        replacement = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
        self.assertEqual(len(original), len(replacement))
        staged = self.root / 'external.tmp'
        staged.write_bytes(replacement)
        os.utime(staged, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        os.replace(staged, path)
        self.assertEqual(path.stat().st_size, original_stat.st_size)
        self.assertEqual(path.stat().st_mtime_ns, original_stat.st_mtime_ns)
        changed = self.read()
        self.assertEqual(changed['settings']['materials']['result_limit'], 21)
        self.assertNotEqual(changed['revision'], saved['revision'])

    def test_failed_replace_preserves_old_file_and_removes_only_own_temporary_files(self):
        saved = self.update(self.read())
        path = self.root / 'workspace-settings.json'
        original = path.read_bytes()
        unrelated = self.root / 'user-note.tmp'
        unrelated.write_text('must keep', encoding='utf-8')
        changed = deepcopy(saved['settings'])
        changed['materials']['result_limit'] = 21
        with patch.object(workspace_settings.os, 'replace', side_effect=OSError('synthetic replace failure')):
            self.assert_error('INVALID_ARGUMENT', lambda: self.update(saved, changed))
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.read(), saved)
        self.assertEqual({p.name for p in self.root.iterdir()}, {'workspace-settings.json', 'user-note.tmp'})
        self.assertEqual(unrelated.read_text(encoding='utf-8'), 'must keep')

    def test_directory_oversized_schema_boolean_nan_and_duplicate_json_are_rejected(self):
        defaults = self.read()['settings']
        path = self.root / 'workspace-settings.json'
        path.mkdir()
        self.assert_error('INVALID_ARGUMENT', self.read)
        path.rmdir()
        valid = {'schema_version': 1, 'settings': defaults}
        bad_schema = deepcopy(valid); bad_schema['schema_version'] = 2
        bool_schema = deepcopy(valid); bool_schema['schema_version'] = True
        bool_budget = deepcopy(valid); bool_budget['settings']['reading']['budget']['model_calls'] = True
        nan_budget = deepcopy(valid); nan_budget['settings']['materials']['budget']['read_bytes'] = float('nan')
        bad_values = [b' ' * (64 * 1024 + 1), *[json.dumps(v).encode() for v in
                      (bad_schema, bool_schema, bool_budget, nan_budget)],
                      ('{"schema_version":1,"schema_version":1,"settings":' + json.dumps(defaults) + '}').encode()]
        for raw in bad_values:
            with self.subTest(prefix=raw[:60]):
                path.write_bytes(raw)
                self.assert_error('INVALID_ARGUMENT', self.read)
                self.assertEqual(path.read_bytes(), raw)

    def test_concurrent_threads_with_same_revision_have_exactly_one_winner(self):
        saved = self.update(self.read())
        barrier = threading.Barrier(2)
        def attempt(limit):
            changed = deepcopy(saved['settings'])
            changed['materials']['result_limit'] = limit
            barrier.wait(timeout=5)
            try:
                return ('saved', self.update(saved, changed)['settings']['materials']['result_limit'])
            except MemoryError as exc:
                return (exc.code, limit)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, (21, 22)))
        self.assertEqual(sorted(item[0] for item in results), ['VERSION_CONFLICT', 'saved'])
        winner = next(limit for status, limit in results if status == 'saved')
        self.assertEqual(self.read()['settings']['materials']['result_limit'], winner)
        self.assertFalse((self.root / 'workspace-settings.json.lock').exists())


if __name__ == "__main__":
    unittest.main()
