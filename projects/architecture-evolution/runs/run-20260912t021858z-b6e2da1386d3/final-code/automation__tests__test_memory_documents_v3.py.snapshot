"""N01–N05: synthetic technical units, fixed documents and bounded contexts.

Pure payload helpers are also reusable by the real Windows upgrade fixture.
No model, network, actual scientific experiment, or production research is used.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_memory_research as fixture
from memory import api, contracts, documents, index, owners, packets, search, technical_units
from memory.errors import MemoryError
import evidence


def unit_payload():
    """Complete synthetic method; unknown scopes are explicit, never blank."""
    return {'unit_type': 'method', 'retrieval_description': {
        'question': '合成温标换算的定义', 'method': '按温度基准和单位换算',
        'key_findings': ['只证明合成流程可读'], 'applicable': ['摄氏温标的合成输入'],
        'not_applicable': ['不得直接用于华氏温标或现实测量'], 'limitations': ['未验证传感器误差']},
        'run_ref': None, 'evidence_refs': [], 'blocks': [
            {'block_id': 'definitions', 'role': 'definitions', 'markdown': '必要定义 ONLY_DEFINITION；$T$ 的单位为 K。', 'requires_block_ids': []},
            {'block_id': 'result', 'role': 'results', 'markdown': '完整过程 ONLY_FULL_RESULT：$T=t+273.15$。', 'requires_block_ids': ['definitions']},
            {'block_id': 'optional', 'role': 'appendix', 'markdown': '未选择的 OPTIONAL_BLOCK。', 'requires_block_ids': []}],
        'figures': [], 'missing_refs': []}


def section_payload(unit_ref, *, key='method', role='methods', selected=None):
    unit = {'type': 'unit', 'ref': deepcopy(unit_ref)}
    if selected is not None:
        unit['block_ids'] = list(selected)
    return {'section_key': key, 'title': '合成章节 ' + key, 'role': role,
        'blocks': [{'type': 'prose', 'markdown': '本章固定说明。', 'evidence_refs': []}, unit],
        'watch_refs': [], 'missing_refs': []}


def document_payload(section_refs, *, document_type='research_process'):
    return {'document_type': document_type, 'purpose': '验证合成研究文档', 'audience': '研究人员',
        'scope': '仅合成软件验收', 'common_refs': [], 'section_refs': deepcopy(section_refs),
        'watch_refs': [], 'missing_refs': []}


class DocumentV3Tests(unittest.TestCase):
    setUp = fixture.ResearchTests.setUp
    put = fixture.ResearchTests.put
    operation = fixture.ResearchTests.operation
    request = fixture.ResearchTests.request
    save = fixture.ResearchTests.save

    def create(self, kind, payload, **kwargs):
        return self.save(self.operation(kind, payload, schema_version=3, body_markdown='', **kwargs))

    def revise(self, record, **changes):
        draft = {key: deepcopy(record[key]) for key in (*contracts.CONTENT_FIELDS, 'schema_version', 'record_reason')}
        draft.update(changes, change_reason='合成修订，保留旧版本')
        return self.save({'op': 'put_record', 'record_id': record['record_id'],
                          'expected_revision': record['revision'], 'draft': draft})

    def pair(self):
        unit = self.create('detail', unit_payload(), discovery='workspace_summary')
        section = self.create('document_section', section_payload(documents.fixed_ref(unit), selected=['result']))
        process = self.create('document', document_payload([documents.fixed_ref(section)]), title='完整研究过程')
        brief_section = self.create('document_section', section_payload(documents.fixed_ref(unit), key='brief', role='conclusion', selected=['result']))
        brief = self.create('document', document_payload([documents.fixed_ref(brief_section)], document_type='research_report'), title='简版研究报告')
        return unit, section, process, brief_section, brief

    def test_n01_unit_contract_and_prerequisites(self):
        draft = self.operation('detail', unit_payload(), schema_version=3)['draft']
        good = contracts.validate_record(draft)
        self.assertTrue(good['valid'], good['errors'])
        selected, required = technical_units.select_blocks(good['record'], ['result'])
        self.assertEqual([block['block_id'] for block in selected], ['definitions', 'result'])
        self.assertEqual(required, ['definitions'])
        for mutation in ('missing', 'cycle', 'duplicate', 'experiment', 'empty_boundary', 'duplicate_body'):
            value = deepcopy(draft)
            if mutation == 'missing':
                value['payload']['blocks'][1]['requires_block_ids'] = ['absent']
            elif mutation == 'cycle':
                value['payload']['blocks'][0]['requires_block_ids'] = ['result']
            elif mutation == 'duplicate':
                value['payload']['blocks'].append(deepcopy(value['payload']['blocks'][0]))
            elif mutation == 'experiment':
                value['payload']['unit_type'] = 'experiment'
            elif mutation == 'empty_boundary':
                value['payload']['retrieval_description']['not_applicable'] = ['  ']
            else:
                value['body_markdown'] = '重复权威全文'
            self.assertFalse(contracts.validate_record(value)['valid'], mutation)
        run = evidence.read(self.root / 'runs/attempt/run.json')
        draft['payload'].update(unit_type='experiment', run_ref={'target_kind': 'owner', 'target_id': 'RUN-R',
            'revision': None, 'sha256': evidence.fingerprint(run), 'locator': '', 'relation': 'input'})
        self.save({'op': 'put_record', 'client_key': 'experiment', 'draft': draft})

    def test_n02_two_fixed_documents_and_independent_chapter_revisions(self):
        unit, section, process, brief_section, brief = self.pair()
        request = {'owner_id': 'RES-R', 'document_id': process['record_id'], 'revision': 1}
        old = api.dispatch(self.service, 'document', request)
        self.assertEqual(old['items'], [])
        self.assertEqual(old['document_source'], 'independent')
        block = old['report']['sections'][0]['blocks'][1]
        self.assertEqual(block['required_block_ids'], ['definitions'])
        self.assertNotIn('optional', [b['block_id'] for b in block['resolved_blocks']])
        brief_view = api.dispatch(self.service, 'document', {'owner_id': 'RES-R', 'document_type': 'research_report'})
        self.assertEqual(brief_view['document']['record_id'], brief['record_id'])
        self.assertEqual(brief_view['report']['sections'][0]['blocks'][1]['ref'], block['ref'])
        value = deepcopy(section['payload']); value['blocks'][0]['markdown'] = '新版章节连接。'
        self.revise(section, payload=value)
        again = api.dispatch(self.service, 'document', request)
        self.assertEqual(again['report']['sections'], old['report']['sections'])
        self.assertEqual(self.service.inspect('RES-R', record_id=brief_section['record_id'])['record']['record_hash'], brief_section['record_hash'])
        with patch.object(technical_units, 'select_blocks', side_effect=AssertionError('outline parsed block body')):
            outline = api.dispatch(self.service, 'outline', request)
        self.assertNotIn('ONLY_FULL_RESULT', json.dumps(outline))
        self.assertEqual(outline['sections'][0]['ref'], documents.fixed_ref(section))

    def test_n03_context_budget_and_excluded_prerequisite(self):
        unit, section, process, _other, _brief = self.pair()
        unrelated = self.create('document_section', {'section_key': 'unrelated', 'title': '无关附录', 'role': 'appendix',
            'blocks': [{'type': 'prose', 'markdown': 'UNRELATED_LARGE_BODY ' * 10000, 'evidence_refs': []}], 'watch_refs': [], 'missing_refs': []})
        payload = deepcopy(process['payload']); payload['section_refs'].append(documents.fixed_ref(unrelated))
        process = self.revise(process, payload=payload)
        request = {'owner_id': 'RES-R', 'document_id': process['record_id'], 'section_id': section['record_id'], 'budget': {'max_chars': 2000}}
        value = api.dispatch(self.service, 'section-context', request)
        self.assertIn('ONLY_DEFINITION', value['context_text'])
        self.assertIn('ONLY_FULL_RESULT', value['context_text'])
        self.assertNotIn('OPTIONAL_BLOCK', value['context_text'])
        self.assertNotIn('UNRELATED_LARGE_BODY', value['context_text'])
        self.assertLessEqual(len(value['context_text']), 2000)
        self.assertTrue(value['manifest']['complete'])
        blocked = api.dispatch(self.service, 'section-context', {**request, 'selection': {'exclude_ids': [unit['record_id'] + '#definitions']}})
        self.assertNotIn('ONLY_FULL_RESULT', blocked['context_text'])
        self.assertFalse(blocked['manifest']['complete'])
        self.assertIn('EXCLUDED', [item['code'] for item in blocked['manifest']['missing']])
        tiny = api.dispatch(self.service, 'section-context', {**request, 'budget': {'max_chars': 30}})
        self.assertLessEqual(len(tiny['context_text']), 30)
        self.assertTrue(tiny['manifest']['required_not_full'])

    def test_n04_explicit_changes_watch_and_inconsistent_document_bases(self):
        unit, section, process, brief_section, brief = self.pair()
        payload = deepcopy(process['payload']); payload['watch_refs'] = [{'watch_type': 'new_unit', 'owner_id': 'RES-R',
            'baseline_head': None, 'baseline_unit_ids': [unit['record_id']]}]
        process = self.revise(process, payload=payload)
        new_unit = self.create('detail', unit_payload(), title='新的合成单元')
        value = deepcopy(unit['payload']); value['blocks'][1]['markdown'] = '修订后的完整计算'
        newer = self.revise(unit, payload=value)
        changed_section = deepcopy(brief_section['payload']); changed_section['blocks'][1]['ref'] = documents.fixed_ref(newer)
        newer_section = self.revise(brief_section, payload=changed_section)
        changed_brief = deepcopy(brief['payload']); changed_brief['section_refs'] = [documents.fixed_ref(newer_section)]
        self.revise(brief, payload=changed_brief)
        result = api.dispatch(self.service, 'document-impact', {'owner_id': 'RES-R', 'document_id': process['record_id']})
        self.assertEqual(result['scientific_review'], 'not_evaluated')
        codes = {item['code'] for item in result['changes']}
        self.assertTrue({'NEW_REVISION', 'NEW_UNIT_UNCOVERED', 'DOCUMENT_BASIS_MISMATCH'} <= codes)
        self.assertIn(new_unit['record_id'], result['uncovered_unit_ids'])
        self.assertEqual(result['affected_section_ids'], [section['record_id']])
        self.assertEqual(self.service.inspect('RES-R', record_id=process['record_id'])['record']['record_hash'], process['record_hash'])

    def test_n05_short_cross_research_search_and_explicit_full_expansion(self):
        unit, section, process, _other, _brief = self.pair()
        row = index._row(unit, owners.resolve_owner(self.root, 'RES-R'))
        self.assertNotIn('ONLY_FULL_RESULT', json.dumps(row))
        result = search.search(self.root, {'query': '温标', 'purpose': 'exploration', 'vector': 'off'}, record=False)
        ids = {item['canonical_id'] for item in result['candidates']}
        self.assertIn(unit['record_id'], ids)
        self.assertNotIn(section['record_id'], ids)
        self.assertNotIn(process['record_id'], ids)
        context = packets.build_context(self.service, {'owner_id': 'RES-R', 'refs': [documents.fixed_ref(unit)], 'budget': 10000})
        self.assertIn('不得直接用于华氏温标', context['context_text'])
        self.assertNotIn('ONLY_FULL_RESULT', context['context_text'])
        full = packets.expand(self.service, [documents.fixed_ref(unit)], {'owner_id': 'RES-R'}, budget=10000)
        self.assertIn('ONLY_FULL_RESULT', full['context_text'])
        self.assertNotIn('requires_block_ids', full['context_text'])

    def test_n06_body_only_clue_recalls_unit_without_expanding_short_context(self):
        unit, section, process, _other, _brief = self.pair()
        payload = deepcopy(unit['payload'])
        payload['blocks'][1]['markdown'] += ' zqxbodyonlyneedle'
        unit = self.revise(unit, payload=payload)
        result = search.search(self.root, {'query': 'zqxbodyonlyneedle', 'purpose': 'exploration',
                                          'vector': 'off'}, record=False)
        ids = {item['canonical_id'] for item in result['candidates']}
        self.assertIn(unit['record_id'], ids)
        self.assertNotIn(section['record_id'], ids)
        self.assertNotIn(process['record_id'], ids)
        # Discovery coverage changes; the caller still chooses how much body to read.
        context = packets.build_context(self.service, {'owner_id': 'RES-R',
            'refs': [documents.fixed_ref(unit)], 'budget': 10000})
        self.assertNotIn('ONLY_FULL_RESULT', context['context_text'])

        from material_query.budget import DEFAULT_BUDGET
        from material_query.contracts import AssociationOptions, DefinitionRef, QueryRequest, Scope
        from material_query.coordinator import Coordinator
        from material_query.wire import json_value
        scope = Scope(('RES-R',), None, None, None, None, None, None, False, (), (), None, None)
        app = Coordinator(self.root)
        self.addCleanup(app.executor.shutdown)
        query = QueryRequest(DefinitionRef('full', '1'), 'zqxbodyonlyneedle', (), scope, scope,
            'exploration', AssociationOptions('off', 'existing-relations', '1', 2, .15, None),
            DEFAULT_BUDGET, 'current', 5, 'reject', (), '', channels=('lexical',), content_source='technical')
        result = app.search(json_value(query))
        self.assertEqual(result['status'], 'ok', result)
        candidate = next(c for c in result['value']['candidates'] if c['refs'][0]['id'] == unit['record_id'])
        hit = candidate['hits'][0]
        self.assertEqual(hit['representation_refs'][0]['locator'], 'block:result')
        self.assertEqual(hit['representation_refs'][0]['sha256'], unit['record_hash'])
        self.assertIn('zqxbodyonlyneedle', hit['matched_text'])
        # Search returns the full unit identity, so assembly closes definitions.
        receipt = result['value']
        packet = app.assemble({'query_id': receipt['query_id'], 'candidate_ids': [candidate['candidate_id']],
                               'expected_request_digest': receipt['request_digest']})
        self.assertIn('ONLY_DEFINITION', str(packet))
        self.assertIn('zqxbodyonlyneedle', str(packet))
        # A later edit removes the clue. Explicit historical lookup still binds
        # the old block, while the default current lookup no longer finds it.
        from dataclasses import replace
        payload['blocks'][1]['markdown'] = '新版本已移除测试词'
        self.revise(unit, payload=payload)
        current = app.search(json_value(query))
        self.assertFalse(current['value']['candidates'], current)
        past = app.search(json_value(replace(query, freshness='allow_stale')))
        old = next(c for c in past['value']['candidates'] if c['refs'][0]['id'] == unit['record_id'])
        self.assertEqual(old['refs'][0]['sha256'], unit['record_hash'])
        self.assertEqual(old['hits'][0]['representation_refs'][0]['locator'], 'block:result')
        self.assertIn('zqxbodyonlyneedle', old['hits'][0]['matched_text'])

    def test_n05_current_restriction_hides_old_unit_and_wrong_hash_is_rejected(self):
        unit, section, process, _other, _brief = self.pair()
        bad = section_payload({**documents.fixed_ref(unit), 'sha256': '0' * 64})
        with self.assertRaises(MemoryError):
            self.create('document_section', bad)
        # The save succeeds, then the fixture's automatic inspect is correctly
        # denied; verify the committed head before testing the read endpoints.
        with self.assertRaises(MemoryError):
            self.revise(unit, sensitivity='restricted')
        state = self.service.store.read_snapshot(owners.resolve_owner(self.root, 'RES-R'))
        self.assertEqual(state['records'][unit['record_id']]['revision'], 2)
        result = api.dispatch(self.service, 'document', {'owner_id': 'RES-R', 'document_id': process['record_id']})
        self.assertIsNone(result['report']['sections'][0]['blocks'][1]['item'])
        self.assertNotIn('ONLY_FULL_RESULT', json.dumps(result))
        self.assertFalse(result['report']['complete'])
        blocked = packets.expand(self.service, [documents.fixed_ref(unit)], {'owner_id': 'RES-R'}, budget=10000)
        self.assertNotIn('ONLY_FULL_RESULT', blocked['context_text'])

    def test_n05_revocation_hides_cited_prose_and_unit_together(self):
        path = self.put('research/topic/input.txt', 'SYNTHETIC INPUT ONLY')
        ref = {'target_kind': 'file', 'target_id': 'SRC-V3', 'revision': None,
               'sha256': evidence.sha256(path), 'locator': '', 'relation': 'input'}
        source = {'source_id': 'SRC-V3', 'path': 'research/topic/input.txt', 'enabled': True}
        self.put('retrieval/sources.json', {'sources': [source]})
        payload = unit_payload(); payload['evidence_refs'] = [ref]
        unit = self.create('detail', payload, sources=[ref])
        payload = section_payload(documents.fixed_ref(unit), selected=['result'])
        payload['blocks'][0].update(markdown='REVOKED_PROSE_SECRET', evidence_refs=[documents.fixed_ref(unit)])
        section = self.create('document_section', payload)
        document = self.create('document', document_payload([documents.fixed_ref(section)]))
        self.put('retrieval/sources.json', {'sources': [{**source, 'enabled': False}]})
        value = api.dispatch(self.service, 'document', {'owner_id': 'RES-R', 'document_id': document['record_id']})
        self.assertNotIn('REVOKED_PROSE_SECRET', json.dumps(value))
        self.assertNotIn('ONLY_FULL_RESULT', json.dumps(value))
        self.assertFalse(value['report']['complete'])

    def test_n05_old_unversioned_drafts_and_missing_brief_are_not_relabelled(self):
        from test_memory_contracts import draft
        old = draft('detail'); old.pop('schema_version')
        result = contracts.validate_record(old)
        self.assertTrue(result['valid'], result['errors'])
        self.assertEqual(result['record']['schema_version'], 2)
        report = {'version': 1, 'title': '旧完整报告', 'sections': [{'section_id': 'old', 'title': '旧章节',
            'role': 'introduction', 'blocks': [{'type': 'prose', 'markdown': 'LEGACY_LONG_PROCESS', 'evidence_refs': []}]}]}
        mapping = draft('map'); mapping.pop('schema_version'); mapping['payload']['report'] = report
        self.assertEqual(contracts.validate_record(mapping)['record']['schema_version'], 2)
        self.save(self.operation('map', mapping['payload'], title='旧地图'))
        process = api.dispatch(self.service, 'document', {'owner_id': 'RES-R'})
        self.assertEqual(process['document_source'], 'legacy_report')
        brief = api.dispatch(self.service, 'document', {'owner_id': 'RES-R', 'document_type': 'research_report'})
        self.assertIsNone(brief['report'])
        self.assertNotIn('LEGACY_LONG_PROCESS', json.dumps(brief))

    def test_n02_brief_prose_covers_unit_without_requiring_every_owner_unit(self):
        unit = self.create('detail', unit_payload())
        extra = self.create('detail', unit_payload(), title='其他研究分支')
        section = self.create('document_section', {'section_key': 'brief', 'title': '简版结论', 'role': 'conclusion',
            'blocks': [{'type': 'prose', 'markdown': '仅归纳本范围的固定发现', 'evidence_refs': [documents.fixed_ref(unit)]}],
            'watch_refs': [], 'missing_refs': []})
        brief = self.create('document', document_payload([documents.fixed_ref(section)], document_type='research_report'))
        result = api.dispatch(self.service, 'document', {'owner_id': 'RES-R', 'document_id': brief['record_id']})
        self.assertTrue(result['report']['complete'])
        self.assertEqual(result['report_coverage']['included_detail_ids'], [unit['record_id']])
        self.assertEqual(result['report_coverage']['uncovered_detail_ids'], [extra['record_id']])


if __name__ == '__main__':
    unittest.main()
