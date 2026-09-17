"""证据页按真实保存结构交付正文；图片只沿登记身份读取。"""
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from types import SimpleNamespace
from unittest.mock import patch
from material_query import evidence_navigation as nav


class EvidenceContentTests(unittest.TestCase):
    def test_document_expands_fixed_sections_and_detail_blocks(self):
        ref = dict(target_kind='record', target_id='MEM-section', revision=2, sha256='s', locator='', relation='contains')
        unitref = dict(ref, target_id='MEM-unit', sha256='u', revision=1)
        unit = dict(record_id='MEM-unit', kind='detail', level='L1', title='实验', body_markdown='', payload={'blocks':[{'block_id':'result','markdown':'完整实验 $x=1$'}]})
        section = dict(record_id='MEM-section', kind='document_section', level=None, title='方法', body_markdown='', payload={'blocks':[{'type':'prose','markdown':'先论证','evidence_refs':[]},{'type':'detail','ref':unitref}]})
        doc = dict(record_id='MEM-doc', kind='document', level=None, title='报告', body_markdown='', payload={'section_refs':[ref]})
        catalog = SimpleNamespace(record=lambda rid, revision: {'MEM-section':section,'MEM-unit':unit}[rid], authorize=lambda value:None)
        section['record_hash']='s'; unit['record_hash']='u'
        body, sections = nav.record_content(catalog, doc)
        self.assertIn('先论证', body)
        self.assertIn('完整实验 $x=1$', body)
        self.assertEqual(sections[0]['id'], 'MEM-section')

    def test_layer_payload_does_not_drop_material_knowledge(self):
        for kind, payload, expected in [('overview',{'overview':'总体认识','limitations':['边界']},'总体认识'),
            ('experience',{'recommendation':'可用方法','applicability':'限定工况'},'限定工况'),
            ('narrative',{'events':[{'summary':'实验经过'}]},'实验经过')]:
            body, _ = nav.record_content(SimpleNamespace(),dict(kind=kind, body_markdown='',payload=payload))
            self.assertIn(expected, body)
        # Confirmation is read from canonical review records, independent of
        # successful saving/execution. Changing the selected content invalidates
        # the binding without rewriting the original review history.
        from memory.contracts import canonical_hash
        claim = {'claim_id':'CL-A','statement':'合成结论','scope':'合成条件'}
        record = dict(record_id='MEM-A',owner_id='RES-A',content_hash='old',payload={'claims':[claim]})
        review = dict(kind='review',payload=dict(target_claim_id='CL-A',target_content_hash='old',state='accepted'),
                      sources=[dict(target_kind='claim',target_id='CL-A',sha256=canonical_hash(claim))])
        catalog = SimpleNamespace(records={'REV-A':{'owner_id':'RES-A'}},record=lambda rid:review,authorize=lambda value:None)
        self.assertTrue(nav.review_metadata(catalog,record)[0]['content_matches'])
        record['content_hash']='new'
        self.assertFalse(nav.review_metadata(catalog,record)[0]['content_matches'])
        catalog.records={}
        self.assertEqual(nav.review_metadata(catalog,record)[0]['state'],'not-reviewed')
        catalog.records={'REV-HIDDEN':{'owner_id':'RES-A'}}
        catalog.record=lambda rid: (_ for _ in ()).throw(ValueError('restricted'))
        self.assertEqual(nav.review_metadata(catalog,record)[0]['state'],'unavailable')

    def test_registered_raster_requires_hash_and_current_permission(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path=root/'figure.png'
            raw=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jX1kAAAAASUVORK5CYII=')
            path.write_bytes(raw)
            catalog=SimpleNamespace(root=root,access=None,service=SimpleNamespace(_file=lambda ref:(path,{'sha256':hashlib.sha256(raw).hexdigest()})))
            ref={'target_id':'SRC-image','sha256':hashlib.sha256(raw).hexdigest()}
            image=nav.raster_media(catalog,ref)
            self.assertTrue(image['data_url'].startswith('data:image/png;base64,'))
            with self.assertRaises(ValueError): nav.raster_media(catalog,dict(ref,sha256='0'*64))
            catalog.service._file=lambda ref: (_ for _ in ()).throw(ValueError('revoked'))
            with self.assertRaises(ValueError): nav.raster_media(catalog,ref)

    def test_unlocated_refs_remain_bibliography_not_invented_inline(self):
        ref=dict(kind='record',id='MEM-actual',revision=1,sha256='a'*64,locator=None)
        text, refs=nav.render_content_citations('没有保存引用位置的段落。',[ref],{'MEM-actual':'真实来源'})
        self.assertTrue(text.startswith('没有保存引用位置的段落。\n\n'))
        self.assertNotIn('本节依据',text)
        self.assertIn('参考文献',text)
        # The author's [1] is explicitly bound to MEM-method, even when storage
        # references enumerate another source first. Never emit a conflicting
        # automatically renumbered bibliography or silently relink plain [1].
        method=dict(ref,id='MEM-method',revision=4)
        text,_=nav.render_content_citations('方法依据[1]。\n\n## 固定依据\n\n[1] 方法说明，MEM-method r4。',
            [ref,method],{'MEM-actual':'其他来源','MEM-method':'方法说明'})
        self.assertIn('方法依据[1]',text)
        self.assertIn('[1] 方法说明，[固定版本 r4]',text)
        self.assertNotIn('### 参考文献',text)
        self.assertNotIn('[2](',text)
        older=dict(method,revision=3,sha256='b'*64)
        text,_=nav.render_content_citations('[1] 方法，MEM-method r4。\n\n未指定版本 MEM-method。\n\n`MEM-method r3`\n\n[已有链接](#/evidence?id=MEM-method)',
            [older,method],{'MEM-method':'方法'})
        self.assertIn('[固定版本 r4]',text)
        self.assertNotIn('[固定版本 r3]',text)
        self.assertIn('未指定版本 MEM-method。',text)
        self.assertIn('固定引用缺口',text)
        self.assertIn('`MEM-method r3`',text)
        self.assertIn('[已有链接](#/evidence?id=MEM-method)',text)

    def test_structural_document_refs_are_not_scientific_citations(self):
        section=dict(target_kind='record',target_id='MEM-section',revision=1,sha256='a',locator='',relation='contains')
        source=dict(section,target_id='MEM-source',relation='supports')
        refs=nav.citation_sources({'kind':'document','sources':[source],'payload':{'section_refs':[section]}})
        self.assertEqual([ref['target_id'] for ref in refs],['MEM-source'])


if __name__ == '__main__': unittest.main()


import test_memory_documents_v3 as document_fixture
from workbench_app import web


class EvidenceApiTests(document_fixture.DocumentV3Tests):
    def test_registered_tool_identity_uses_registry_member(self):
        self.put('tools/registry.json',{'tools':[{'tool_id':'TOOL-TEST','title':'合法工具'}]})
        from memory import index
        db=index.connect(self.root)
        # Exercise the same persisted Owner row seen in the real workspace.
        db.execute('INSERT INTO memory_owners VALUES (?,?,?,?,?,?)',('TOOL-TEST','tool',json.dumps({'path':'tools/registry.json','id_field':'tool_id','id_value':'TOOL-TEST'}),'unused',None,0))
        db.commit()
        db.close()
        catalog=nav.Catalog(self.root)
        self.addCleanup(catalog.close)
        self.assertEqual(catalog.owner('TOOL-TEST')['title'],'合法工具')
        self.assertFalse(any('索引Owner' in warning for warning in catalog.warnings))
        member=nav.native_registration({'tools':[{'tool_id':'TOOL-TEST','title':'合法工具'}]},
            {'id_field':'tool_id','id_value':'TOOL-TEST'},'tool')
        self.assertEqual(member['title'],'合法工具')

    def test_image_api_and_document_figure_namespace(self):
        raw=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jX1kAAAAASUVORK5CYII=')
        path=self.root/'figure.png';path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
        self.put('retrieval/sources.json',{'sources':[dict(source_id='SRC-IMAGE',path='figure.png',owner_id='RES-R',enabled=True,sensitivity='internal',sha256=sha)]})
        ref=dict(target_kind='file',target_id='SRC-IMAGE',revision=None,sha256=sha,locator='',relation='supports')
        sections=[]
        for position in range(2):
            payload=document_fixture.unit_payload()
            payload['blocks'][1]['markdown']+='\n\n![image](figure:0)'
            payload['figures']=[dict(caption='图'+str(position),ref=ref)]
            unit=self.create('detail',payload)
            section=self.create('document_section',document_fixture.section_payload(document_fixture.documents.fixed_ref(unit),key='s'+str(position),selected=['result']))
            sections.append(document_fixture.documents.fixed_ref(section))
        doc=self.create('document',document_fixture.document_payload(sections))
        service=SimpleNamespace(root=self.root,materials=SimpleNamespace(access_owner_ids=['RES-R']))
        result=web.post(service,'evidence/detail',{'id':doc['record_id']})
        self.assertEqual(len(result['images']),2)
        self.assertIn('(figure:0)',result['content_markdown']);self.assertIn('(figure:1)',result['content_markdown'])
        self.assertIn('SRC-IMAGE',[item['id'] for item in result['references']])
        image=web.post(service,'evidence/detail',{'id':'SRC-IMAGE','sha256':sha})
        self.assertTrue(image['media']['data_url'].startswith('data:image/png'))
        self.assertNotIn('未读取原件',image['content_markdown'])
        service.materials.access_owner_ids=['RUN-R']
        with self.assertRaises(ValueError):web.post(service,'evidence/detail',{'id':'SRC-IMAGE'})
        service.materials.access_owner_ids=['RES-R']
        self.put('retrieval/sources.json',{'sources':[dict(source_id='SRC-IMAGE',path='figure.png',owner_id='RES-R',enabled=False,sha256=sha)]})
        with self.assertRaises(Exception):web.post(service,'evidence/detail',{'id':doc['record_id']})

    def test_document_api_resolves_fixed_unit_selection(self):
        unit, section, process, _, _ = self.pair()
        service=SimpleNamespace(root=self.root,materials=SimpleNamespace(access_owner_ids=None))
        result=web.post(service,'evidence/detail',{'id':process['record_id']})
        self.assertIn('ONLY_FULL_RESULT',result['content_markdown'])
        self.assertIn('ONLY_DEFINITION',result['content_markdown'])
        self.assertNotIn('OPTIONAL_BLOCK',result['content_markdown'])
        self.assertNotIn('检索说明',result['content_markdown'])
        self.assertNotIn('技术单元类型',result['content_markdown'])
        self.assertTrue(all(item['title']!='固定来源' for item in result['references']))
        self.assertEqual(result['sections'][0]['id'],section['record_id'])
        service.materials.access_owner_ids=[]
        with self.assertRaises(ValueError): web.post(service,'evidence/detail',{'id':process['record_id']})


for _name in dir(document_fixture.DocumentV3Tests):
    if _name.startswith('test_') and _name not in EvidenceApiTests.__dict__: setattr(EvidenceApiTests,_name,None)
