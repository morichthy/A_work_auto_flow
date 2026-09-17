"""Recover the receipt-name collision without changing any registered evidence.

The original capture used document.json for both a record and its assembled
report. Preserve its fixed receipts, read a fresh baseline after concurrent
updates, and store the assembled document under a distinct name. No product
code or historical record is edited directly.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

RUN = Path(__file__).resolve().parents[1]
ROOT = RUN.parents[3]
OUT = RUN / '.run-captures' / 'memory-closure'
BASE = OUT / 'baseline-current'
OLD = RUN / '.run-captures' / 'memory-baseline'
sys.path.insert(0, str(ROOT / 'automation/scripts'))


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def save(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if path.exists() and path.read_text(encoding='utf-8') != text:
        raise RuntimeError('Refuse to replace a different receipt: ' + str(path))
    path.write_text(text, encoding='utf-8')


def prepare():
    from memory import api
    from memory.service import MemoryService
    service = MemoryService(ROOT)
    owner_id = 'PRJ-ARCHITECTURE-EVOLUTION'
    BASE.mkdir(parents=True, exist_ok=True)
    # The registration fixes hashes for these receipts. Check them before reuse.
    registered = load(RUN / 'run.json')
    for entry in registered['artifacts']:
        if '/memory-baseline/' in entry['path']:
            path = ROOT / entry['path']
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            expected = entry.get('sha256') or entry.get('fingerprint')
            if digest != expected:
                raise RuntimeError('Registered baseline fingerprint mismatch')
    def call(action, request):
        result = api.dispatch(service, action, request)
        if result.get('error'):
            raise RuntimeError(result['error'])
        return result
    start = call('inspect', {'owner_id': owner_id})
    save(BASE / 'owner-start.json', start)
    records = {}
    for key in ('unit', 'section', 'document', 'overview'):
        record_id = load(OLD / (key + '.json'))['record']['record_id']
        value = call('inspect', {'owner_id': owner_id, 'record_id': record_id})
        save(BASE / (key + '.json'), value)
        record = value['record']
        records[key] = {field: record[field] for field in ('revision', 'record_hash')}
        records[key]['record_id'] = record['record_id']
    request = {'owner_id': owner_id, 'document_id': records['document']['record_id'],
               'revision': records['document']['revision']}
    save(BASE / 'document-request.json', request)
    save(BASE / 'outline.json', call('outline', request))
    for action, name in [('document', 'document-assembled.json'), ('document-impact', 'document-impact.json')]:
        save(BASE / name, call(action, request))
        print('Saved ' + name, flush=True)
    end = call('inspect', {'owner_id': owner_id})
    save(BASE / 'owner-end.json', end)
    if start['head'] != end['head']:
        raise RuntimeError('Concurrent Owner change during baseline recovery')
    save(BASE / 'manifest.json', {
        'head': start['head'], 'records': records,
        'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in BASE.glob('*.json') if p.name != 'manifest.json'},
        'recovery': 'record and assembled report use distinct names; original fixed receipts untouched',
    })
    print('Baseline recovered; read document-assembled.json before apply.', flush=True)


def apply():
    path = RUN / 'scripts/apply_budget_trace_results.py'
    spec = importlib.util.spec_from_file_location('fixed_budget_record', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.BASELINE = BASE
    module.OUT = OUT / 'root-apply'
    sys.argv = [str(path), '--run-json', str(RUN / 'run.json'), '--results', str(RUN / 'RESULTS.md'),
                '--conclusion-file', str(OUT / 'reviewed-conclusion.md')]
    module.main()


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) == 2 else ''
    if mode == 'prepare':
        prepare()
    elif mode == 'apply':
        apply()
    else:
        raise SystemExit('Usage: finish_budget_record.py prepare|apply')
