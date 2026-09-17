"""Check delivered public receipts; this does not bypass memory permissions."""
import json
from pathlib import Path
OUT = Path(__file__).parent
def read(name):
    return json.loads((OUT / (name + '.json')).read_text(encoding='utf-8'))
baseline = read('baseline-owner')
old_document = read('baseline-document')
new_document = read('final-document')
receipt = read('overview-document-commit')
new_doc = read('overview-document-MEM-bd121869-a0b9-59e3-af23-8e8675374a63')['record']
new_overview = read('overview-document-MEM-b8db41b4-3a97-5f26-ba21-87f6cce7d155')['record']
old_doc = baseline['records'][new_doc['record_id']]
old_overview = baseline['records'][new_overview['record_id']]
checks = {
    'independent_document': new_document['document_source'] == 'independent',
    'document_complete': new_document['report']['complete'],
    'no_missing': not new_document['missing'],
    'old_section_unchanged': new_document['report']['sections'][0] == old_document['report']['sections'][0],
    'old_section_refs_preserved': new_doc['payload']['section_refs'][:-1] == old_doc['payload']['section_refs'],
    'overview_old_body_preserved': new_overview['body_markdown'].startswith(old_overview['body_markdown']),
    'overview_old_technical_refs_preserved': new_overview['payload']['technical_refs'][:-1] == old_overview['payload']['technical_refs'],
    'old_coverage_exclusions_unchanged': new_document['report_coverage']['uncovered_detail_ids'] == old_document['report_coverage']['uncovered_detail_ids'],
    'head_consistent': all(value == receipt['commit_id'] for value in new_document['basis_heads'].values()),
    'indexed': receipt['index_status'] == 'indexed',
}
(OUT / 'readback-checks.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2),encoding='utf-8')
print(json.dumps(checks, ensure_ascii=False, indent=2))
if not all(checks.values()): raise SystemExit(1)
# Output the new assembled section for actual AI reading. Historical section
# bytes have been checked equal to the already fully read fixed baseline.
new_section = new_document['report']['sections'][-1]
parts = ['# ' + new_section['title']]
for block in new_section['blocks']:
    if block['type'] == 'prose': parts.append(block['markdown'])
    else: parts.extend(item['markdown'] for item in block['resolved_blocks'])
(OUT / 'new-assembled-section.md').write_text('\n\n'.join(parts),encoding='utf-8')
print('new-assembled-section.md saved')
