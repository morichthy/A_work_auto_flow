"""知识正文与派工状态分离；诊断字段不能因清理正文而丢失。"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import unittest
from material_query.reading_owner import handoff_value

class NoteKnowledgeTests(unittest.TestCase):
    def test_bracketed_known_id_is_one_citation_without_touching_links(self):
        from material_query.reading_citations import render
        ref=dict(kind='record',id='MEM-known',revision=1,sha256='a'*64,locator=None)
        value,_=render('依据[MEM-known]；`[MEM-known]`；[链接](https://example.org/MEM-known)',[ref])
        self.assertNotIn('依据[[1]]',value)
        self.assertIn('依据[1]',value)
        self.assertIn('`[MEM-known]`',value)
        self.assertIn('[链接](https://example.org/MEM-known)',value)
    def test_owner_body_excludes_planning_but_keeps_knowledge_and_gaps(self):
        note=dict(question='不要重复的问题',understanding='真正的材料认识',conditions=[],logic=[],details=['$x=1$'],
                  limitations=['材料边界'],next_steps=['材料中建议验证温度'],sources=[])
        session=dict(goal='编排目标',conditions=['检索条件'],phase='ask_user',decisions=[dict(next_step='expand',reason='派工原因',outcome='派工结果')],
            owner_notes={'A':note},candidates={},owner_progress={},rounds=[],context={'note_max_tokens':6000},mode='owner_document')
        result=handoff_value(session)
        for text in ('编排目标','派工原因','派工结果','不要重复的问题'): self.assertNotIn(text,result['context_markdown'])
        self.assertIn('真正的材料认识',result['context_markdown'])
        self.assertIn('可选的下一步建议',result['context_markdown'])
        self.assertTrue(result['needs_user_input'])
        self.assertIn('等待用户意见',result['gaps'])

    def test_legacy_body_excludes_status_and_decision_but_reports_gaps(self):
        from test_reading_handoff_view import ReadingHandoffViewTests
        from material_query.reading_delegation import handoff_value as legacy
        session=ReadingHandoffViewTests().session()
        session.update(goal='编排目标',conditions=['检索条件'],phase='ask_user',decisions=[dict(next_step='expand',reason='派工原因',outcome='派工结果')])
        result=legacy(session)
        for text in ('编排目标','派工原因','派工结果','等待用户意见','本次展示'): self.assertNotIn(text,result['context_markdown'])
        self.assertIn('等待用户意见',result['gaps'])
        session['phase']='finish'
        session['decisions'][0]['reason']='很长的派工原因'*20000
        finished=legacy(session)
        self.assertTrue(finished['complete'])
        self.assertEqual(finished['gaps'],[])

    def test_quick_synthesis_uses_same_knowledge_body_contract(self):
        from material_query.wire import digest
        from material_query.reading_strategy import accepted_sources
        note=dict(question='不应重述',understanding='片段覆盖认识',conditions=[],logic=[],details=[],limitations=['仅片段'],next_steps=[],sources=[])
        session=dict(goal='编排目标',phase='finish',decisions=[],owner_notes={},candidates={},owner_progress={},rounds=[],context={'note_max_tokens':6000},mode='owner_document',strategy='quick')
        session['synthesis_note']={**note,'owner_notes_digest':digest({}),'accepted_sources_digest':digest(accepted_sources(session))}
        result=handoff_value(session)
        self.assertTrue(result['synthesis_included'])
        self.assertNotIn('编排目标',result['context_markdown']); self.assertNotIn('不应重述',result['context_markdown'])
        self.assertNotIn('可选的下一步建议',result['context_markdown'])
        self.assertIn('仅片段',result['context_markdown'])


import test_reading_owner_document as owner_fixture


class NoteKnowledgeApiTests(owner_fixture.OwnerDocumentTests):
    def test_reader_can_save_clue_without_inventing_next_query(self):
        read=self.owner_read()
        note=self.research_note(read['document_refs'])
        note['exploration_clues']=[dict(text='材料提及温度边界',reason='可能影响迁移',sources=read['document_refs'][:1],next_query='',limitations=['未验证'])]
        result=self.call('note',owner_id=self.fx.owner_ids['A'],research_note=note)
        self.assertEqual(result['status'],'ok',result)

for _name in dir(owner_fixture.OwnerDocumentTests):
    if _name.startswith('test_') and _name not in NoteKnowledgeApiTests.__dict__:setattr(NoteKnowledgeApiTests,_name,None)
