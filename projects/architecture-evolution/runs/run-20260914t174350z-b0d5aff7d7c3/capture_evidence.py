"""固定本轮代码和已发生回执；只复制显式输入，不重新评定测试或业务质量。

由run-execute登记输入/输出和真实退出码。快照创建在其独立output目录内，
不修改源文件；文件缺失/路径越界/错误回执与预期不符时返回非零。
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('inputs', type=Path, nargs='+')
    args = parser.parse_args()
    root, output = args.repository.resolve(), args.output.resolve()
    rows = []
    for source in args.inputs:
        source = source.resolve()
        if not source.is_relative_to(root):
            parser.error('固定输入必须位于本次已授权工作区')
        relative = source.relative_to(root)
        content = source.read_bytes()
        destination = output / 'snapshot' / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as stream:
            stream.write(content)
        rows.append({'path': relative.as_posix(), 'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)})
        if source.name == 'ai-view-budget-result.json':
            receipt = json.loads(content.decode('utf-8-sig'))
            if receipt.get('code') != 'BUDGET' or receipt.get('value') is not None:
                raise RuntimeError('CLI失败边界回执与实际验证目标不符')
    manifest = {'captured_at': datetime.now(timezone.utc).isoformat(), 'files': rows,
                'scope': '源码与已发生回执固定，不是测试重执行或业务复核', 'scientific_review': 'not-reviewed'}
    (output / 'source-and-evidence.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'captured_files': len(rows), 'manifest': str(output / 'source-and-evidence.json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
