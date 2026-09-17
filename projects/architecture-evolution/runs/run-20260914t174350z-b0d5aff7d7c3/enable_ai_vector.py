"""在已有合成夹具中启用本机离线向量，不联网、不修改原模型或业务索引。"""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    run_dir = Path(__file__).resolve().parent
    manifest = json.loads((run_dir / 'ai-fixture.json').read_text(encoding='utf-8'))
    root = Path(manifest['root']).resolve()
    # 必须是本配方建立的隔离夹具，不能通过手改清单把真实业务区作为索引目标。
    if not root.is_relative_to(repository / '.local') or not (root / 'SYNTHETIC_ONLY.txt').is_file():
        parser.error('只能处理.local下明确标记的合成夹具')
    sys.path[:0] = [str(repository / 'automation/tests'), str(repository / 'automation/scripts')]
    from test_memory_associations_real import install_model_links
    from memory import index
    install_model_links(root, source_root=repository)
    result = index.sync_owner(root, manifest['scope_owner'], vector='required')
    (run_dir / 'ai-vector-index.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    if result['index_status'] != 'indexed':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
