"""隔离真实AI验收：prepare / call ACTION REQUEST_JSON_PATH / finalize。

每次call新建并关闭Coordinator，沿同RS/账本；完整回执仅供reader读取。
准备者不代填理解；finalize只输出体积计量，不回显正文。
"""
import argparse
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import socket
import sys
import tempfile
import uuid

RUN = Path(__file__).resolve().parents[1]
REPO = RUN.parents[3]
VERIFY = RUN / 'verification'
META = VERIFY / 'ai-fixture'
TRANSCRIPT = VERIFY / 'ai-transcript'
sys.path[:0] = [str(REPO / 'automation/scripts'), str(REPO / 'automation/tests')]
from material_query_fixture import materialize
from test_memory_documents_v3 import unit_payload
from memory import contracts
from material_query.api import dispatch
from material_query.budget import DEFAULT_BUDGET
from material_query.contracts import AssociationOptions, DefinitionRef, QueryRequest, Scope
from material_query.coordinator import Coordinator
from material_query.wire import json_value


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name('.pending-' + uuid.uuid4().hex)
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    pending.replace(path)


def offline(*args, **kwargs):
    raise RuntimeError('验收禁止外网；只读取固定获准合成来源')


def invoke(root, owner, action, raw, actor):
    socket.socket.connect = offline
    app = Coordinator(Path(root), access_owner_ids=[owner])
    try:
        result = dispatch(app, action, raw)
    finally:
        app.close()
    number = len(list(TRANSCRIPT.glob('*.json'))) + 1
    write(TRANSCRIPT / f'{number:03d}-{actor}-{action}.json', {
        'actor': actor, 'action': action, 'request': raw, 'response': result,
        'response_serialized_chars': len(encode(result)),
        'value_serialized_chars': len(encode(result.get('value')))})
    return result


def long_section(heading, core):
    # 分散保留定义/限制/反例；台账长度只模拟阅读负担，不充当独立实验重复。
    paragraphs = [heading, core]
    for number in range(19):
        paragraphs.append(f'过程检查条目{number+1:02d}：本条为合成台账。记录员先登记输入通道、'
            '仪器型号、环境介质和稳定时间，再抄录原始显示数值；显示数值与修正后数值分栏保存。'
            '条件未知时不得从相邻批次借用条件，不把已经计算出一个数字视为已经验证模型。'
            '每份抄录保留量纲、方向、采样时点以及是否达到平衡。重复记录用于检查程序完整交付长文，'
            '不增加统计样本量，也不提供独立实验重复。后文限制与本段流程冲突时，以明确适用边界为准。')
    return '\n\n'.join(paragraphs)


def prepare():
    if (META / 'state.json').exists():
        raise RuntimeError('已有固定RS；不得重建重置预算')
    boundary = Path(tempfile.mkdtemp(prefix='delegated-reading-ai-'))
    root = boundary / 'workspace'
    fx = materialize(root, isolation_root=boundary)
    # 内容仅写入固定材料/核对文件，不经prepare stdout提供给主Agent。
    sections = [
        ('definitions', 'definitions', '变量与单位',
         '合成NS4探头的x为原始摄氏显示值，b为以°C表示的零点偏差，g为无量纲比例系数；'
         '修正温度记θ，绝对温度记T。温度差1°C与1K大小相同，但绝对零点不同。'),
        ('method', 'methods', '处理顺序',
         '先消除仪器偏差再做温标平移：$$\\theta=(x-b)/g,\\qquad T=\\theta+273.15\\;\\mathrm{K}.$$'
         '合成输入x=20.0°C、b=0.6°C、g=1.02。不得写成T=(x+273.15-b)/g；后者将温标零点也缩放。'),
        ('uncertainty', 'results', '不确定度传播',
         '仅在x、b、g独立且一阶线性近似成立时：'
         '$$u_\\theta^2=(u_x/g)^2+(u_b/g)^2+((x-b)u_g/g^2)^2.$$'
         'u_x和u_b单位°C，u_g无量纲，u_θ单位°C。273.15为温标定义的精确平移常数，'
         '不额外贡献该模型中的标准不确定度；u_T与u_θ数值相同，单位K。'),
        ('conditions', 'limitations', '适用条件',
         '仅适用于NS4、干燥空气、热平衡状态以及修正温度θ在[-10,60]°C内。'
         '边界针对修正后的θ，不是未经校准的x。g和b来自同一校准版本；'
         '缺版本、热瞬态、液体浸入或换NS7均不能直接复用。'),
        ('counterexample', 'appendix', '关键反例',
         '若b和g由同一次拟合估计且具有非零协方差，独立性平方和不是完整不确定度。'
         '必须按梯度与完整协方差矩阵计算u²=JΣJᵀ并保留交叉项；不能因为误差条很小而忽略相关性。'
         '热瞬态下即便θ仍在区间内也不满足平衡假设。缺协方差时应明确缺口，不能编造为零。')]
    draft = {key: deepcopy(fx.records['A.unit'][key]) for key in
             (*contracts.CONTENT_FIELDS, 'schema_version', 'record_reason')}
    payload = unit_payload()
    payload['retrieval_description'].update(question='Northstar温度换算阅读验收',
        method='固定方法与适用边界阅读', key_findings=['需阅读全文核对变量、条件和反例'], limitations=['仅合成验收'])
    payload['blocks'] = [{'block_id': bid, 'role': role, 'markdown': long_section(title, core),
        'requires_block_ids': [] if bid == 'definitions' else ['definitions']}
        for bid, role, title, core in sections]
    draft.update(title='Northstar温度换算完整方法', body_markdown='', payload=payload,
                 sources=[fx.source_ref('A')], keywords=['Northstar阅读验收'])
    fx.commit_draft('ai.main', draft)
    drafts = {'main': deepcopy(draft)}
    for label, title, body in [
        ('near', 'Northstar旧型号摘记', '对象NS7、液体浸入且未达到热平衡。不能仅凭同名字段迁移到NS4方法。'),
        ('far', 'Northstar刻度说明', '这里只比较摄氏华氏刻度，不定义NS4仪器增益或零点，不能替代校准证据。')]:
        item = deepcopy(draft)
        item['title'] = title
        item['payload']['blocks'] = [{'block_id': 'context', 'role': 'definitions', 'markdown': body, 'requires_block_ids': []}]
        drafts[label] = deepcopy(item)
        fx.commit_draft('ai.' + label, item)
    write(META / 'fixed-inputs.json', drafts)
    write(META / 'sealed-expectations.json', {'not_reader_brief': True,
        'checks': [core for _, _, _, core in sections],
        'main_body_chars': sum(len(b['markdown']) for b in payload['blocks']),
        'refs': {key: fx.refs[key] for key in ['ai.main', 'ai.near', 'ai.far']}})
    owner = fx.owner_ids['A']
    scope = Scope((owner,), None, None, None, None, None, None, False, (), (), None, None)
    sid = 'RS-' + str(uuid.uuid4())
    goal = '阅读Northstar温度换算材料，判断方法能否复用；保留公式、变量单位、适用条件、误差处理与反例，区分相似但不适用材料。仅合成验收，不认可现实工程结论。'
    query = QueryRequest(DefinitionRef('full', '1'), 'Northstar阅读验收', (), scope, scope, 'exploration',
        AssociationOptions('off', 'existing-relations', '1', 0, 0.0, None),
        replace(DEFAULT_BUDGET, model_calls=6, model_tokens=3072, model_input_tokens=3072),
        'current', 3, 'skip', (), '')
    response = invoke(root, owner, 'reading-start', {'session_id': sid, 'goal': goal,
        'conditions': ['只读本RS获准固定合成材料，不递归委派，不伪造缺失工况。'],
        'query': json_value(query), 'reranking': {'mode': 'off', 'candidate_limit': 3, 'conditions': []}}, 'setup')
    if response['status'] != 'ok':
        raise RuntimeError('start失败，详见setup回执')
    state = {'root': str(root), 'owner_id': owner, 'session_id': sid,
             'revision': response['value']['revision'], 'goal': goal, 'scope': json_value(scope)}
    write(META / 'state.json', state)
    write(META / 'empty.json', {})
    write(META / 'recall-request.json', {'question': 'Northstar阅读验收', 'keywords': ['Northstar阅读验收'],
         'scope': json_value(scope), 'reason': '实际完整阅读固定方法与干扰材料'})
    print(encode({**state, 'driver': str(Path(__file__).resolve()),
        'usage': 'call reading-view empty.json; call reading-recall recall-request.json；随后按回执read/note/decide；RS/revision/request_id可省，driver沿固定RS补全。'}))


def call(action, request_path, actor):
    state = json.loads((META / 'state.json').read_text(encoding='utf-8'))
    raw = json.loads(Path(request_path).read_text(encoding='utf-8-sig'))
    raw.setdefault('session_id', state['session_id'])
    if raw['session_id'] != state['session_id']:
        raise RuntimeError('driver只允许本次固定RS')
    if action not in {'reading-view', 'reading-delegate', 'reading-handoff'}:
        raw.setdefault('expected_revision', state['revision'])
        raw.setdefault('request_id', str(uuid.uuid4()))
    result = invoke(state['root'], state['owner_id'], action, raw, actor)
    if isinstance(result.get('value'), dict) and 'revision' in result['value']:
        state['revision'] = result['value']['revision']
        write(META / 'state.json', state)
    print(encode(result))
    if result.get('status') not in {'ok', 'partial'}:
        raise SystemExit(2)


def finalize():
    logs = [json.loads(p.read_text(encoding='utf-8')) for p in sorted(TRANSCRIPT.glob('*.json'))]
    reader = [row for row in logs if row['actor'] == 'reader']
    handoffs = [row for row in logs if row['action'] == 'reading-handoff']
    report = {'reader_response_serialized_chars': sum(row['response_serialized_chars'] for row in reader),
        'reader_calls': len(reader), 'handoff_response_chars': [row['response_serialized_chars'] for row in handoffs],
        'handoff_value_chars': [row['value_serialized_chars'] for row in handoffs],
        'limitation': '字符体积不是宿主模型token或费用；主侧不加载原始材料。'}
    write(VERIFY / 'ai-reading-size-report.json', report)
    print(encode(report))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('prepare')
    item = sub.add_parser('call')
    item.add_argument('action')
    item.add_argument('request_json_path')
    item.add_argument('--actor', choices=['reader', 'main'], default='reader')
    sub.add_parser('finalize')
    args = parser.parse_args()
    if args.command == 'prepare': prepare()
    elif args.command == 'call': call(args.action, args.request_json_path, args.actor)
    else: finalize()


if __name__ == '__main__':
    main()
