"""本轮AI拟定请求的CLI传输与回执归档；不代替AI对结果的实际阅读判断。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent.parent / 'verification'


def call(root, label, args):
    result = subprocess.run([sys.executable, str(ROOT / 'automation/scripts/workspace_cli.py'), *args],
                            cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=30)
    (HERE / (label + '.stdout.json')).write_text(result.stdout, encoding='utf-8')
    (HERE / (label + '.stderr.log')).write_text(result.stderr, encoding='utf-8')
    if result.returncode:
        raise RuntimeError((label, result.returncode, result.stderr, result.stdout))
    return json.loads(result.stdout)


with tempfile.TemporaryDirectory(prefix='settings-ai-cli-') as directory:
    root = Path(directory)
    (root / 'workspace.json').write_text('{"schema_version":1}', encoding='utf-8')
    before = call(root, 'cli-01-show', ['workspace-settings', 'show'])
    # 由本轮主AI选择的合成任务：主Agent独立完成，默认交付3项，
    # 明确关闭重排，输出预算6000字符；不修改正式工作区偏好。
    changed = before['settings']
    changed['collaboration']['subagents'] = 'off'
    changed['reading']['result_limit'] = 3
    changed['reading']['reranking'] = {'mode': 'off', 'candidate_limit': 3}
    changed['reading']['budget']['output_chars'] = 6000
    request = {'expected_revision': before['revision'], 'settings': changed}
    request_path = root / 'settings-request.json'
    request_path.write_text(json.dumps(request, ensure_ascii=False), encoding='utf-8')
    (HERE / 'cli-settings-request.json').write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding='utf-8')
    call(root, 'cli-02-save', ['workspace-settings', 'set', '--request', str(request_path)])
    policy = call(root, 'cli-03-policy', ['workspace-settings', 'policy'])
    template = call(root, 'cli-04-template', ['material-query', 'reading-template'])
    print(json.dumps({'policy': policy, 'reading': {'result_limit': template['value']['query']['result_limit'],
        'output_chars': template['value']['query']['budget']['output_chars'],
        'reranking': template['value']['reranking']},
        'scope': '隔离临时工作区；主AI须回读上述原始输出并作实际判断，脚本不生成AI通过结论'}, ensure_ascii=False, indent=2))
