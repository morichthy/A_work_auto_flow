"""公开CLI完整读取已选择的合成候选；正文由主线AI实际阅读后再保存理解。"""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cli_reranking_smoke import cli, HERE

handoff = json.loads((HERE / 'cli-smoke-handoff.json').read_text(encoding='utf-8'))
result = cli(Path(handoff['root']), 'reading-read', {
    'session_id': handoff['session_id'], 'expected_revision': handoff['revision'],
    'request_id': 'cli-ai-full-read-1',
    'candidate_ids': [row['id'] for row in handoff['candidates']]})
print(json.dumps(result, ensure_ascii=False, indent=2))
