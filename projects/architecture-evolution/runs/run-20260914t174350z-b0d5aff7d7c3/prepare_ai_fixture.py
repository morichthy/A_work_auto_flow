"""建立独立合成材料，供真实AI通过公开CLI阅读；不会编写AI阅读笔记。

输入为源码目录，输出为.local隔离夹具与本Run内的固定身份清单。
原始业务数据不读写。重复执行拒绝覆盖已有夹具，异常返回非零。
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    run_dir = Path(__file__).resolve().parent
    boundary = repository / '.local' / ('bilingual-query-' + run_dir.name)
    target = boundary / 'synthetic-workspace'
    if target.exists():
        parser.error('夹具已存在，拒绝覆盖已发生的阅读记录')
    sys.path[:0] = [str(repository / 'automation/tests'), str(repository / 'automation/scripts')]
    from material_query_fixture import materialize
    from test_memory_documents_v3 import unit_payload
    from memory import contracts

    fx = materialize(target, isolation_root=boundary)
    # 仅在合成知识中设置正反例；标签不作为AI已阅读或检索正确的回执。
    for label, version, statement in (
        ('bilingual.good', 'v2.1', 'Retain the error constraint ≤ 0.5 mm in each equivalent query.'),
        ('bilingual.wrong-version', 'v2.0', 'This earlier version drops numerical constraints during query translation.'),
    ):
        draft = {key: deepcopy(fx.records['A.unit'][key]) for key in
                 (*contracts.CONTENT_FIELDS, 'schema_version', 'record_reason')}
        payload = unit_payload()
        payload['blocks'] = [
            {'block_id': 'definitions', 'role': 'definitions',
             'markdown': f'SYNTHETIC ONLY: X200 {version} is an invented retrieval system. mm denotes millimetres.',
             'requires_block_ids': []},
            {'block_id': 'method', 'role': 'methods',
             'markdown': 'Query expansion for cross-lingual information retrieval uses bilingual equivalent queries. '
                         + statement + ' Related terms are exploration hints, not equivalent conditions.',
             'requires_block_ids': ['definitions']},
        ]
        draft.update(title=f'SYNTHETIC ONLY X200 {version} retrieval note', body_markdown='', payload=payload,
                     keywords=['X200', version, 'query expansion'], sources=[fx.source_ref('A')])
        fx.commit_draft(label, draft)
    shutil.copyfile(repository / 'retrieval/query-terms.json', target / 'retrieval/query-terms.json')
    manifest = {'scope_owner': fx.owner_ids['A'], 'root': str(target),
                'expected_refs': {label: fx.ref(label).__dict__ if hasattr(fx.ref(label), '__dict__') else fx.ref(label)
                                  for label in ['bilingual.good', 'bilingual.wrong-version']}}
    (run_dir / 'ai-fixture.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    main()
