"""隔离临时设置的cold/warm读取探针，不代表检索查询加速。

Cold仅表示进程缓存未命中，未清空操作系统文件缓存。每次warm仍付出
root.resolve、lstat、线程锁和深拷贝成本；不设固定微秒通过阈值。
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import statistics
import sys
import tempfile
import time
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[5])
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'verification/settings-cache.json')
    parser.add_argument('--iterations', type=int, default=2000)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error('--iterations must be positive')
    root = args.root.resolve()
    sys.path.insert(0, str(root / 'automation/scripts'))
    import workspace_settings
    with tempfile.TemporaryDirectory(prefix='settings-cache-') as temp:
        seed, measured = Path(temp) / 'seed', Path(temp) / 'measured'
        seed.mkdir()
        measured.mkdir()
        initial = workspace_settings.read(seed)
        workspace_settings.update(seed, {'expected_revision': initial['revision'], 'settings': initial['settings']})
        # 用新根使cold不受update已缓存结果影响；只操作本次合成临时目录。
        shutil.copy2(seed / 'workspace-settings.json', measured / 'workspace-settings.json')
        samples = []
        original_loads = workspace_settings.json.loads
        with patch.object(workspace_settings.json, 'loads', wraps=original_loads) as loads:
            started = time.perf_counter_ns()
            first = workspace_settings.read(measured)
            cold_ms = (time.perf_counter_ns() - started) / 1_000_000
            cold_decodes = loads.call_count
            for _ in range(args.iterations):
                started = time.perf_counter_ns()
                current = workspace_settings.read(measured)
                samples.append((time.perf_counter_ns() - started) / 1_000_000)
                if current != first:
                    raise AssertionError('unchanged settings changed during warm reads')
            warm_decodes = loads.call_count - cold_decodes
        if cold_decodes != 1 or warm_decodes != 0:
            raise AssertionError(f'expected cold=1/warm=0 JSON decodes, got {cold_decodes}/{warm_decodes}')
    result = {
        'schema_version': 1, 'status': 'passed', 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'settings read only in synthetic temporary roots; not material query performance',
        'platform': platform.platform(), 'python': sys.version, 'iterations': args.iterations,
        'cold_read_ms': cold_ms,
        'warm_read_ms': {'p50': statistics.median(samples),
                         'p95': sorted(samples)[max(0, math.ceil(len(samples) * .95) - 1)],
                         'min': min(samples), 'max': max(samples)},
        'json_decodes': {'cold': cold_decodes, 'warm': warm_decodes},
        'percentile_method': 'nearest rank for p95; statistics.median for p50',
        'threshold': None,
        'remaining_cost': 'Every read still resolves/checks the root, stats the settings path, locks and deep-copies the snapshot.',
        'limitations': ['Single machine/process synthetic settings; no cross-machine claim.',
                       'Cold means process cache miss; OS filesystem cache is not flushed.',
                       'No retrieval-quality, material-IO, model-inference or end-to-end query benchmark.'],
        'source_sha256': {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in (Path(workspace_settings.__file__), Path(__file__).resolve())}}
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    # 同目录原子发布，避免工作区发现器看到空文件/半份JSON。
    fd, staging_name = tempfile.mkstemp(prefix='settings-cache-', suffix='.tmp', dir=output.parent)
    staging = Path(staging_name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staging, output)
    finally:
        staging.unlink(missing_ok=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
