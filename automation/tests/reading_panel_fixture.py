"""通过公开动作生成阅读面板的合成数据，不直接写RS/规范memory文件。"""
import uuid
import base64
import hashlib
import json
import struct
import zlib
import evidence
from memory.service import MemoryService
from material_query.api import dispatch
from material_query.coordinator import Coordinator


def populate(root):
    oid='RES-SYNTHETIC'
    service=MemoryService(root)
    run_ref={'target_kind':'owner','target_id':'RUN-SYNTHETIC','revision':None,
             'sha256':evidence.EvidenceGraph(root).nodes['RUN-SYNTHETIC']['fingerprint'],
             'locator':'','relation':'supports'}
    draft={'schema_version':4,'owner_id':oid,'kind':'overview','title':'面板固定方法',
           'body_markdown':'panelreading 前提：绝对温度，偏置为273.15；这是合成展示资料，未验证现实方法。',
           'keywords':['panelreading'],'sources':[run_ref],'provenance_gap':'纯合成UI测试输入，非真实依据',
           'record_reason':'面板端到端测试','sensitivity':'internal','discovery':'workspace_summary',
           'payload':{'question':'阅读面板是否可用','methods':['查看'],'results':['待测试'],'current_stage':'合成',
                      'open_questions':[],'claims':[],'process_refs':[],'technical_refs':[],'experience_refs':[], 'limitations':['非业务结论']}}
    receipt=service.commit({'schema_version':3,'owner_id':oid,'expected_head':None,'request_id':str(uuid.uuid4()),
                            'actor':{'kind':'workflow','id':'SYNTHETIC-E2E'},'operations':[{'op':'put_record','client_key':'overview','draft':draft}]})
    assert receipt['save_status']=='committed',receipt
    # Real public memory commits exercise the same document/figure identities
    # as user records; the tiny raster is explicitly synthetic local evidence.
    from test_memory_documents_v3 import unit_payload, section_payload, document_payload
    from memory.documents import fixed_ref
    image_path=root/'research/synthetic-panel.png'
    image_path.parent.mkdir(parents=True,exist_ok=True)
    # A visible 64px checker makes browser screenshots meaningful; build a
    # standard RGB PNG using the standard library, without a renderer dependency.
    def png_chunk(kind,data):
        return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    pixels=b''.join(b'\0'+b''.join(bytes((30,110,180) if (x//8+y//8)%2 else (240,190,70)) for x in range(64)) for y in range(64))
    image_path.write_bytes(b'\x89PNG\r\n\x1a\n'+png_chunk(b'IHDR',struct.pack('!2I5B',64,64,8,2,0,0,0))+png_chunk(b'IDAT',zlib.compress(pixels))+png_chunk(b'IEND',b''))
    image_hash=hashlib.sha256(image_path.read_bytes()).hexdigest()
    registry_path=root/'retrieval/sources.json'
    registry=json.loads(registry_path.read_text(encoding='utf-8-sig')) if registry_path.exists() else {'sources':[]}
    registry['sources'].append(dict(source_id='SRC-PANEL-FIGURE',path='research/synthetic-panel.png',owner_id=oid,enabled=True,sensitivity='internal',sha256=image_hash))
    registry_path.parent.mkdir(parents=True,exist_ok=True)
    registry_path.write_text(json.dumps(registry,ensure_ascii=False),encoding='utf-8')
    image_ref=dict(target_kind='file',target_id='SRC-PANEL-FIGURE',revision=None,sha256=image_hash,locator='',relation='supports')
    def put_content(kind,payload,title):
        head=service.inspect(oid)['head']
        content={**draft,'schema_version':3,'kind':kind,'title':title,'body_markdown':'','payload':payload,'sources':[run_ref]}
        saved=service.commit({'schema_version':3,'owner_id':oid,'expected_head':head['commit_id'],'request_id':str(uuid.uuid4()),
            'actor':{'kind':'workflow','id':'SYNTHETIC-E2E'},'operations':[{'op':'put_record','client_key':kind,'draft':content}]})
        row=saved['record_results'][0]
        return service.inspect(oid,row['revision'],record_id=row['record_id'])['record']
    payload=unit_payload()
    payload['blocks'][1]['markdown']+='\n\n![合成图](figure:0)'
    payload['figures']=[{'caption':'合成受控图片','ref':image_ref}]
    unit=put_content('detail',payload,'证据面板合成技术单元')
    section=put_content('document_section',section_payload(fixed_ref(unit),selected=['result']),'证据面板固定章节')
    document=put_content('document',document_payload([fixed_ref(section)]),'证据面板完整文稿')
    (root/'evidence-panel-fixture.json').write_text(json.dumps({'document_id':document['record_id'],'unit_id':unit['record_id'],'image_id':'SRC-PANEL-FIGURE'}),encoding='utf-8')
    app=Coordinator(root)
    def create_session(goal, understanding):
        template=dispatch(app,'reading-template',{})['value']
        template.update(owner_id=oid,goal=goal,conditions=['保留单位与前提'])
        started=dispatch(app,'reading-start',template);assert started['status']=='ok',started
        revision=1
        def call(action,**fields):
            nonlocal revision
            result=dispatch(app,'reading-'+action,dict(session_id=template['session_id'],expected_revision=revision,request_id=str(uuid.uuid4()),**fields))
            assert result['status'] in {'ok','partial'},result
            revision=result['value']['revision']
            return result['value']
        recalled=call('recall',question='panelreading',keywords=[],scope=template['query']['scope'],reason='面板合成检查')
        assert recalled['candidates'][0]['owner_id'] == oid
        # 当前默认按Owner完整阅读；保留真实读取回执中的固定引用，不伪造已读来源。
        document=call('read',owner_id=oid)
        call('note',owner_id=oid,research_note={
            'question':'阅读面板是否保留必要细节','conditions':['绝对温度'],
            'understanding':understanding,'logic':['核对显示的单位前提'],
            'details':['绝对温度偏置273.15',r'行内公式 \(T=t+273.15\)，展示公式 \[\Delta T=0.01\]'],
            'sources':document['document_refs'],
            'limitations':['合成测试'],'next_steps':['检查阅读面板']})
    try:
        # 两个真实公开会话，后建立的主会话保持旧UI基线的默认选择。
        create_session('辅助合成问题','第二问题的独立理解')
        create_session('合成阅读会话','合成阅读理解：保留前提')
    finally:app.close()
