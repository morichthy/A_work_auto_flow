"""Isolated, synthetic reading exercise through the public material API.

This helper creates no production knowledge and writes no AI notes by itself.
An independent reader must inspect returned text, author its own notes and send
normal API requests. Persisted receipts make the actual interaction auditable.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[3]
sys.path[:0] = [str(WORKSPACE / 'automation/scripts'), str(WORKSPACE / 'automation/tests')]


def initialize():
    """Create controlled documents using existing public commit fixtures."""
    from material_query_fixture import materialize, _draft
    from test_memory_documents_v3 import unit_payload, section_payload, document_payload
    from memory.documents import fixed_ref
    # The shared fixture deliberately refuses any production-workspace subtree.
    # Keep the synthetic database in a dedicated OS temporary directory; the
    # run stores its manifest and receipts, never production data copies.
    folder = Path(tempfile.mkdtemp(prefix='reading-three-modes-ai-'))
    root = folder / 'workspace'
    if root.exists():
        raise RuntimeError('Fixture already exists; do not overwrite earlier AI evidence.')
    fx = materialize(root, isolation_root=folder)
    cases = {
        'A': ('phase_case 相位误差排查', '相位误差与时间抖动', [
            '这是合成教学模型，不是实际仪器实验。f 为信号频率（Hz），dt 为采样时刻误差（s），dphi 为相位误差（rad）。',
            '小时间误差模型：$dphi=2\\pi f\\,dt$。取 f=1000 Hz、dt=1e-6 s，得到 dphi≈0.006283 rad。',
            '本材料没有解释时间抖动来自哪里。可探索过零检测阈值波动；该提示只是方向，尚未验证电源与相位之间的联系。']),
        'B': ('crossing_case 过零检测', '阈值扰动的时间偏移', [
            '这是合成线性化模型。dv 为阈值电压扰动（V），S 为过零附近电压斜率（V/s），dt 为时间偏移（s）。',
            '局部线性、斜率非零且扰动很小时，$dt\\approx dv/S$。取 dv=0.001 V、S=1000 V/s，则 dt=1e-6 s。',
            '斜率接近零或波形非线性时不能直接套用。这里只讨论阈值扰动，不证明电源纹波就是扰动来源；需要独立测量供电到阈值的传递。'])}
    refs = {}
    for alias, (title, question, paragraphs) in cases.items():
        payload = unit_payload()
        payload['retrieval_description'].update(question=question, method=question,
            key_findings=[paragraphs[1]], applicable=['合成小扰动模型'],
            not_applicable=['大扰动或未经验证的真实系统'], limitations=[paragraphs[2]])
        for block, paragraph in zip(payload['blocks'], paragraphs):
            block['markdown'] = paragraph
        draft = _draft(fx, alias, 'detail', title, payload)
        draft['keywords'] = [title.split()[0], question]
        unit = fx.commit_draft(alias + '.ai_unit', draft)
        section = fx.commit_draft(alias + '.ai_section', _draft(fx, alias, 'document_section', title,
            section_payload(fixed_ref(unit))))
        document = fx.commit_draft(alias + '.ai_document', _draft(fx, alias, 'document', title,
            document_payload([fixed_ref(section)])))
        refs[alias] = {'owner_id': fx.owner_ids[alias], 'document_ref': fixed_ref(document)}
    manifest = {'root': str(root), 'owners': refs, 'goal': '解释合成phase_case中的相位误差，找出可验证的上游线索。',
                'limitations': ['合成材料；无现实实验；不证明检索质量普遍提升']}
    (HERE / 'AI_FIXTURE.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def dispatch_request(action, request_path):
    """Only the existing public API writes RS state; every result is retained."""
    from material_query.api import dispatch
    from material_query.coordinator import Coordinator
    raw = json.loads(Path(request_path).read_text(encoding='utf-8-sig'))
    manifest = json.loads((HERE / 'AI_FIXTURE.json').read_text(encoding='utf-8'))
    app = Coordinator(Path(manifest['root']))
    try:
        result = dispatch(app, action, raw)
    finally:
        app.close()
    receipts = HERE / 'ai-receipts'
    receipts.mkdir(exist_ok=True)
    sequence = len(list(receipts.glob('*.json'))) + 1
    (receipts / f'{sequence:03d}-{action}.json').write_text(json.dumps(
        {'action': action, 'request': raw, 'response': result}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', help='init or a public reading-* action')
    parser.add_argument('--request', help='UTF-8 JSON request, required for API actions')
    args = parser.parse_args()
    if args.action == 'init':
        initialize()
    elif args.request:
        dispatch_request(args.action, args.request)
    else:
        parser.error('--request is required for reading actions')
