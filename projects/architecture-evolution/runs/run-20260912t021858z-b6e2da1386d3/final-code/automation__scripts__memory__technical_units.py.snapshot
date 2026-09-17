"""Version-three technical units: short discovery text and complete blocks.

The description is authored knowledge with explicit transfer limits. It is not
generated during reads. Complete Markdown remains in one canonical block list;
selecting a result closes only its declared local prerequisites, never file or
record permissions, exclusions, or the caller's context budget.
"""
from copy import deepcopy
import re

from .errors import MemoryError


DESCRIPTION_LABELS = (
    ('question', '问题'), ('method', '方法'), ('key_findings', '主要发现'),
    ('applicable', '适用条件'), ('not_applicable', '不适用条件'), ('limitations', '限制'))


def is_unit(record):
    return record.get('kind') == 'detail' and record.get('schema_version') == 3


def description_text(record):
    """Keep every applicability boundary in both discovery and short contexts."""
    if not is_unit(record):
        return record.get('body_markdown', '')
    description = record['payload']['retrieval_description']
    lines = []
    for key, label in DESCRIPTION_LABELS:
        value = description[key]
        text = '\n'.join('- ' + item for item in value) if isinstance(value, list) else value
        lines.append(label + '：\n' + text)
    return '\n\n'.join(lines)


def block_errors(blocks):
    """Return semantic errors after schema validation has established types."""
    errors, ids = [], set()
    for position, block in enumerate(blocks):
        key = block['block_id']
        # A block identity must be safe in the public MEM-id#block selection.
        if '#' in key or key.strip() != key or not key.strip():
            errors.append((f'/blocks/{position}/block_id', 'Block identity cannot contain # or surrounding whitespace'))
        if key in ids:
            errors.append((f'/blocks/{position}/block_id', 'Duplicate technical block identity'))
        ids.add(key)
        dependencies = block['requires_block_ids']
        if len(dependencies) != len(set(dependencies)):
            errors.append((f'/blocks/{position}/requires_block_ids', 'Duplicate prerequisite block identity'))
    graph = {block['block_id']: block['requires_block_ids'] for block in blocks}
    for position, block in enumerate(blocks):
        if set(block['requires_block_ids']) - ids:
            errors.append((f'/blocks/{position}/requires_block_ids', 'Required technical block is missing'))
    # Iterative DFS avoids recursion limits for an otherwise valid large unit.
    visited, active = set(), set()
    for start in graph:
        stack = [(start, False)]
        while stack:
            node, exiting = stack.pop()
            if exiting:
                active.discard(node)
                visited.add(node)
            elif node in active:
                errors.append(('/blocks', 'Technical block prerequisite cycle'))
                return errors
            elif node not in visited and node in graph:
                active.add(node)
                stack.append((node, True))
                stack.extend((child, False) for child in reversed(graph[node]))
    return errors


def select_blocks(record, block_ids=None):
    """Return canonical-order blocks plus automatically required identities.

    This is a pure selection, not an access check. Callers must validate the
    fixed record and all evidence before returning any selected Markdown.
    """
    if not is_unit(record):
        if block_ids:
            raise MemoryError('INVALID_SCHEMA', '旧详细记录没有可选择的稳定内容块')
        return [], []
    blocks = record['payload']['blocks']
    errors = block_errors(blocks)
    if errors:
        raise MemoryError('INVALID_SCHEMA', '技术单元块依赖无效', errors=[
            {'code': 'INVALID_SCHEMA', 'path': path, 'message': message} for path, message in errors])
    by_id = {block['block_id']: block for block in blocks}
    selected = list(by_id) if block_ids is None else block_ids
    if not isinstance(selected, list) or any(not isinstance(key, str) for key in selected):
        raise MemoryError('INVALID_ARGUMENT', 'block_ids 必须是内容块身份数组')
    if len(set(selected)) != len(selected) or set(selected) - by_id.keys() or not selected:
        raise MemoryError('INVALID_SCHEMA', '所选内容块重复、不存在或为空')
    closure, queue = set(selected), list(selected)
    while queue:
        for dependency in by_id[queue.pop()]['requires_block_ids']:
            if dependency not in closure:
                closure.add(dependency)
                queue.append(dependency)
    return ([deepcopy(block) for block in blocks if block['block_id'] in closure],
            [block['block_id'] for block in blocks if block['block_id'] in closure - set(selected)])


def render_full(record, block_ids=None):
    if not is_unit(record):
        return record.get('body_markdown', '')
    blocks, _ = select_blocks(record, block_ids)
    return '\n\n'.join(block['markdown'] for block in blocks)


def fixed_ref_errors(ref, path, *, record_only=False):
    """New document citations bind full record hashes; old Ref remains intact."""
    errors = []
    if record_only and (ref.get('target_kind') != 'record' or not ref.get('target_id', '').startswith('MEM-')):
        errors.append((path, 'A fixed MEM record reference is required'))
    if not re.fullmatch(r'[0-9a-f]{64}', ref.get('sha256') or ''):
        errors.append((path + '/sha256', 'A fixed SHA-256 is required'))
    if ref.get('target_kind') == 'record' and (type(ref.get('revision')) is not int or ref['revision'] < 1):
        errors.append((path + '/revision', 'A positive fixed revision is required'))
    return errors


def validate_unit(record):
    payload = record['payload']
    errors = block_errors(payload['blocks'])
    for key, value in payload['retrieval_description'].items():
        if any(not text.strip() for text in (value if isinstance(value, list) else [value])):
            errors.append(('/retrieval_description/' + key, 'Describe the condition or explicitly state that it is unknown'))
    for position, block in enumerate(payload['blocks']):
        if not block['markdown'].strip():
            errors.append((f'/blocks/{position}/markdown', 'A complete technical block cannot be blank'))
    run = payload['run_ref']
    if payload['unit_type'] == 'experiment' and run is None:
        errors.append(('/run_ref', 'An experiment needs an actual fixed Run'))
    if run is not None and (run['target_kind'] != 'owner' or not run['target_id'].startswith('RUN-')):
        errors.append(('/run_ref', 'run_ref must identify a native RUN owner'))
    for position, ref in enumerate(payload['evidence_refs']):
        errors.extend(fixed_ref_errors(ref, f'/evidence_refs/{position}'))
    if not payload['evidence_refs'] and run is None and not record['sources'] and not record.get('provenance_gap'):
        errors.append(('/evidence_refs', 'A non-executed unit needs provenance or an explicit gap'))
    if run is not None:
        errors.extend(fixed_ref_errors(run, '/run_ref'))
    for position, block in enumerate(payload['blocks']):
        for match in re.finditer(r'!\[[^\]]*\]\(figure:(\d+)\)', block['markdown']):
            if int(match[1]) >= len(payload['figures']):
                errors.append((f'/blocks/{position}/markdown', 'Inline figure index is not registered in this unit'))
    return errors


def validate_watches(watches):
    """Watch baselines are observations, never reference/support relationships."""
    errors, seen = [], set()
    for position, watch in enumerate(watches):
        path = f'/watch_refs/{position}'
        identity = (watch['watch_type'], watch.get('record_id') or watch.get('owner_id'))
        if identity in seen:
            errors.append((path, 'Duplicate change watch'))
        seen.add(identity)
        if watch['watch_type'] == 'revision':
            if not watch['record_id'].startswith('MEM-') or watch['baseline_revision'] < 1:
                errors.append((path, 'Revision watch needs a MEM identity and positive baseline revision'))
            if not re.fullmatch(r'[0-9a-f]{64}', watch['baseline_record_hash']):
                errors.append((path + '/baseline_record_hash', 'Revision watch needs the observed record hash'))
        elif len(watch['baseline_unit_ids']) != len(set(watch['baseline_unit_ids'])):
            errors.append((path + '/baseline_unit_ids', 'Duplicate observed technical unit identity'))
    return errors


def validate_composition(record, context):
    """Check composition target kinds/order using the existing resolver callback."""
    payload, errors = record['payload'], []
    errors.extend(validate_watches(payload['watch_refs']))
    for key in (('section_key', 'title') if record['kind'] == 'document_section' else ('purpose', 'audience', 'scope')):
        if not payload[key].strip():
            errors.append(('/' + key, 'Authored document metadata cannot be blank'))
    resolver = context.get('resolve_ref')
    if record['kind'] == 'document_section':
        seen = set()
        for position, block in enumerate(payload['blocks']):
            if block['type'] == 'prose':
                for j, ref in enumerate(block['evidence_refs']):
                    errors.extend(fixed_ref_errors(ref, f'/blocks/{position}/evidence_refs/{j}'))
                continue
            ref = block['ref']
            bad = fixed_ref_errors(ref, f'/blocks/{position}/ref', record_only=True)
            errors.extend(bad)
            identity = (ref['target_id'], ref['revision'])
            if identity in seen:
                errors.append((f'/blocks/{position}/ref', 'Duplicate unit in one section; combine its selected blocks'))
            seen.add(identity)
            if not bad and resolver:
                target = resolver(ref)
                if not isinstance(target, dict) or target.get('kind') != 'detail':
                    errors.append((f'/blocks/{position}/ref', 'Unit block must reference a detail record'))
                else:
                    try:
                        select_blocks(target, block.get('block_ids'))
                    except MemoryError as exc:
                        errors.append((f'/blocks/{position}/block_ids', str(exc)))
    else:
        seen, keys, synthesis = set(), set(), False
        for position, ref in enumerate(payload['section_refs']):
            path = f'/section_refs/{position}'
            bad = fixed_ref_errors(ref, path, record_only=True)
            errors.extend(bad)
            if ref['target_id'] in seen:
                errors.append((path, 'Duplicate document section'))
            seen.add(ref['target_id'])
            if not bad and resolver:
                target = resolver(ref)
                if not isinstance(target, dict) or target.get('kind') != 'document_section':
                    errors.append((path, 'Section reference must resolve to a document_section record'))
                    continue
                section = target['payload']
                if section['section_key'] in keys:
                    errors.append((path, 'Duplicate stable section key'))
                keys.add(section['section_key'])
                if section['role'] in {'discussion', 'conclusion'}:
                    synthesis = True
                if synthesis and section['role'] == 'experiment':
                    errors.append((path, 'Experiment sections must precede discussion and conclusion'))
        for position, ref in enumerate(payload['common_refs']):
            errors.extend(fixed_ref_errors(ref, f'/common_refs/{position}'))
    return errors
