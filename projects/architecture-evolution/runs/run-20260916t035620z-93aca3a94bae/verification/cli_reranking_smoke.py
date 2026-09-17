"""创建隔离合成材料，并实际调用公开CLI完成start/recall；不代填AI阅读笔记。"""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(REPO / 'automation/tests'), str(REPO / 'automation/scripts')]
from material_query_fixture import materialize
from test_memory_documents_v3 import unit_payload
from memory import contracts


def cli(root, action, request=None):
    """真实CLI子进程；唯一测试边界是禁止socket联网，未替换召回或模型。"""
    # material-query当前没有--root（仅memory/testing支持）；公开CLI按cwd发现。
    arguments = ['material-query', action]
    if request is not None:
        request_path = HERE / (action + '-request.json')
        preserve(request_path)
        request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding='utf-8')
        arguments += ['--request', str(request_path)]
    bootstrap = "import socket,sys,runpy; socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('offline smoke blocks network')); sys.path.insert(0,sys.argv[1]); sys.argv=sys.argv[2:]; runpy.run_path(sys.argv[0],run_name='__main__')"
    proc = subprocess.run([sys.executable, '-c', bootstrap, str(REPO / 'automation/scripts'),
                           str(REPO / 'automation/scripts/workspace_cli.py'), *arguments],
                          capture_output=True, text=True, encoding='utf-8', cwd=root)
    stdout_path, stderr_path = HERE / (action + '-stdout.log'), HERE / (action + '-stderr.txt')
    preserve(stdout_path)
    preserve(stderr_path)
    stdout_path.write_text(proc.stdout, encoding='utf-8')
    stderr_path.write_text(proc.stderr, encoding='utf-8')
    result = json.loads(proc.stdout)
    if proc.returncode and result.get('status') != 'partial':
        raise RuntimeError(f'{action} exit {proc.returncode}: {proc.stderr}; {proc.stdout[:1000]}')
    return result


def preserve(path):
    """重试保留旧原始回执，失败记录不覆盖。"""
    if path.exists():
        number = 1
        while path.with_name(path.stem + f'-attempt-{number}' + path.suffix).exists():
            number += 1
        path.rename(path.with_name(path.stem + f'-attempt-{number}' + path.suffix))


def main():
    isolation = Path(tempfile.mkdtemp(prefix='reranking-public-cli-'))
    root = isolation / 'workspace'
    if root.exists():
        raise RuntimeError('不覆盖已有隔离工作区与阅读历史')
    fx = materialize(root, isolation_root=isolation)
    shutil.copytree(REPO / 'services/reranker', root / 'services/reranker')
    # 冻结fixture不变：这些材料只验证显式字段与必要定义链路，不并入原评测。
    cases = [
        ('positive', '正例X200低温启动', '型号: X200\n温度: -30 °C\n批准: 是',
         '低温启动验收探针：先预热电池再启动，避免低温启动失败。合成说明，没有真实实验。'),
        ('conflict', '冲突Y200低温启动', '型号: Y200\n温度: -30 °C\n批准: 是',
         '低温启动验收探针：先预热电池再启动；此合成说明仅用于Y200。'),
        ('negation', '否定批准X200', '型号: X200\n温度: -30 °C\n批准: 不是是',
         '低温启动验收探针：本材料不批准直接使用预热程序。'),
        ('unknown', '工况未知启动说明', '型号和温度未记录；批准状态未知。',
         '低温启动验收探针：可考虑预热，但没有已知适用条件。'),
    ]
    for label, title, fields, body in cases:
        draft = {key: deepcopy(fx.records['A.unit'][key]) for key in
                 (*contracts.CONTENT_FIELDS, 'schema_version', 'record_reason')}
        payload = unit_payload()
        payload['blocks'][0]['markdown'] = fields + '\n必要定义：温度指环境温度，单位°C；批准是合成授权字段。'
        payload['blocks'][1]['markdown'] = body
        draft.update(title=title, body_markdown='', payload=payload,
                     sources=[fx.source_ref('A')], keywords=['低温启动验收探针'])
        fx.commit_draft('smoke.' + label, draft)
    return run_session(root, fx.owner_ids['A'])


def run_session(root, owner):
    template = cli(root, 'reading-template')['value']
    scope = template['query']['scope']
    scope['owner_ids'] = [owner]
    template['query']['scope_ceiling'] = deepcopy(scope)
    question = '低温启动验收探针：X200在低于-20°C时，有批准的避免启动失败程序吗？'
    template['query']['question'] = question
    template['query']['result_limit'] = 6
    template['goal'] = '独立合成CLI验收：真实模型、显式条件、必要定义；不证明业务检索质量'
    template['conditions'] = ['仅合成软件验收，不作为工程结论']
    template['reranking'] = {'mode': 'required', 'candidate_limit': 6, 'conditions': [
        {'id': 'device', 'kind': 'literal', 'field': '型号', 'operator': 'eq', 'expected': 'X200'},
        {'id': 'temperature', 'kind': 'numeric', 'field': '温度', 'operator': 'lt', 'expected': -20, 'unit': '°C'},
        {'id': 'approval', 'kind': 'literal', 'field': '批准', 'operator': 'eq', 'expected': '是'}]}
    start = cli(root, 'reading-start', template)
    request = {'session_id': template['session_id'], 'expected_revision': start['value']['revision'],
               'request_id': 'cli-smoke-recall-1', 'question': question, 'keywords': ['低温启动验收探针'],
               'scope': scope, 'reason': '验收真实离线重排与显式条件读取，未代填AI理解'}
    recall = cli(root, 'reading-recall', request)
    handoff = {'root': str(root), 'session_id': template['session_id'],
               'revision': recall.get('value', {}).get('revision'), 'status': recall['status'],
               'candidates': [{'id': row['candidate_id'], 'title': row['title'], 'ranking': row.get('ranking')}
                              for row in recall.get('value', {}).get('candidates', [])]}
    (HERE / 'cli-smoke-handoff.json').write_text(json.dumps(handoff, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(handoff, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    run_session(Path(sys.argv[1]), 'RES-MQ-A') if len(sys.argv) > 1 else main()
