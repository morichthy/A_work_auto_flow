"""冻结本次源码与回执，不覆盖任何已有固定包。仅用于本机研发记录。"""
from pathlib import Path
import hashlib
import json
import sys
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'automation/scripts'))
from deployment import framework_files

target = HERE / '.run-captures/final-evidence'
target.mkdir(parents=True, exist_ok=False)
manifest = {}
groups = {
    'source': [(ROOT / name, name) for name in framework_files(ROOT)],
    'receipts': [(path, path.relative_to(HERE).as_posix()) for path in HERE.rglob('*')
                 if path.is_file() and '.run-captures' not in path.parts
                 and path.name not in {'run.json', 'lineage.jsonl'}],
}
for group, files in groups.items():
    manifest[group] = {}
    with zipfile.ZipFile(target / (group + '.zip'), 'x', zipfile.ZIP_DEFLATED) as archive:
        for path, name in sorted(files, key=lambda item: item[1]):
            raw = path.read_bytes()
            manifest[group][name] = hashlib.sha256(raw).hexdigest()
            archive.writestr(name, raw)
(target / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
for group in groups:
    with zipfile.ZipFile(target / (group + '.zip')) as archive:
        assert all(hashlib.sha256(archive.read(name)).hexdigest() == expected
                   for name, expected in manifest[group].items())
print(json.dumps({'files': {key: len(value) for key,value in manifest.items()}, 'readback_mismatches': 0}, ensure_ascii=False))
