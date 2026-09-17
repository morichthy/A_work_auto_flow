"""主线AI完整读过reading-read回执后，保存实际理解并跨进程恢复验证。"""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cli_reranking_smoke import cli, HERE

handoff = json.loads((HERE / 'cli-smoke-handoff.json').read_text(encoding='utf-8'))
root = Path(handoff['root'])
revision = json.loads((HERE / 'reading-read-stdout.log').read_text(encoding='utf-8'))['value']['revision']
understandings = [
    ('direct', '该合成正例明确给出X200、环境温度-30°C、批准为是；正文主张先预热电池再启动，符合本题三个显式条件。',
     '用于核对重排能同时读取definitions与result；只证明合成流程，不能据此建议实际设备操作。'),
    ('inspiration', '该记录只说可考虑预热，型号、温度和批准均未知；保留候选不表示满足条件。',
     '可作为后续追问适用条件的线索，不能作为本题已批准程序的直接依据。'),
    ('not_useful', '该合成记录匹配X200和-30°C，但明确不批准直接使用预热程序；CE语义高分不消除批准冲突。',
     '作为否定条件反例保留诊断，不作为获准方案。'),
    ('not_useful', '该记录限定Y200，虽有-30°C和批准字段，不能迁移为X200适用。',
     '作为型号冲突反例，检验明确冲突材料降序且证据不丢失。'),
]
for number, (row, (kind, summary, explanation)) in enumerate(zip(handoff['candidates'], understandings), 1):
    result = cli(root, 'reading-note', {
        'session_id': handoff['session_id'], 'expected_revision': revision,
        'request_id': f'cli-ai-note-{number}', 'candidate_id': row['id'], 'summary': summary,
        'connection': {'kind': kind, 'explanation': explanation, 'chain': []},
        'details': [{'text': summary, 'reason': '保存实际条件与正文用途的核对边界', 'block_ids': ['definitions', 'result']}],
        'uncertainties': ['全部是合成软件验收材料，没有真实工程试验或批准证明。']})
    revision = result['value']['revision']
result = cli(root, 'reading-decide', {
    'session_id': handoff['session_id'], 'expected_revision': revision, 'request_id': 'cli-ai-finish-1',
    'direction': 'finish', 'reason': '4个合成候选已完整回读并由主线AI记录理解，排序条件与用途一致。',
    'next_step': '保存回执并继续正式软件回归；真实业务检索质量和延迟另行评估。',
    'outcome': '实际模型评分及明确字段条件、完整阅读、保存理解链路完成；缺dense警告如实保留。',
    'human_decision': ''})
result = cli(root, 'reading-resume', {'session_id': handoff['session_id'],
    'expected_revision': result['value']['revision'], 'request_id': 'cli-ai-resume-1'})
assert len(result['value']['unnoted_candidate_ids']) == 0
assert all('ranking' in row for row in result['value']['candidates'])
print(result['value']['context_markdown'])
