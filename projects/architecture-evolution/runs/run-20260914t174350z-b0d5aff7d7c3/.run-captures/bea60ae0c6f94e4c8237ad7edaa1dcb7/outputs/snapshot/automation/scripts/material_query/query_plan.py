"""Bounded, caller-authored language plans; no translation model runs here.

The maintained dictionary provides navigation terms, never evidence or scope.
Every round freezes the expansion and dictionary fingerprint so continuation
does not silently change meaning after a dictionary edit.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json
import re

from memory import owners
from .validation import QueryError, object_fields
from .wire import digest


PLAN_FIELDS = {'query_variants', 'protected_terms', 'corpus_language', 'language_reason', 'query_domains'}
SOURCE_FIELDS = ('query_plan_id', 'id', 'variant_id', 'language', 'kind', 'channel', 'weight')


def charge_diagnostics(ledger, value):
    """Count new JSON diagnostics once where delivered; existing packet accounting stays intact."""
    ledger.charge('output_chars', len(json.dumps(value, ensure_ascii=False, separators=(',', ':'))))


def require(condition, message):
    if not condition:
        raise QueryError('VALIDATION', message)


def texts(value, name, limit=64):
    require(isinstance(value, list) and len(value) <= limit, name + '必须为有界文本数组')
    require(all(isinstance(item, str) and item.strip() and len(item) <= 1000 for item in value),
            name + '包含无效文本')
    return list(dict.fromkeys(value))


def contains(text, term):
    """ASCII boundaries prevent X200 from matching X2000; Chinese stays literal."""
    return re.search(r'(?<![A-Za-z0-9_])' + re.escape(term) + r'(?![A-Za-z0-9_])', text, re.I) is not None


def numeric_tokens(value):
    return re.findall(r'(?<![A-Za-z0-9])(?:[A-Za-z]+[-_]?)?\d+(?:[._-]\d+)*(?:[A-Za-z]+)?', value)


def preserves(value, term):
    # Preserve case-sensitive model/version identities. Unlike dictionary
    # matching, this check must not equate potentially different identifiers.
    return re.search(r'(?<![A-Za-z0-9_])' + re.escape(term) + r'(?![A-Za-z0-9_])', value) is not None


def dictionary(root, ledger):
    file = owners.safe_path(root, 'retrieval/query-terms.json')
    if not file.exists():
        return [], {'status': 'missing', 'path': 'retrieval/query-terms.json', 'sha256': None}
    size = file.stat().st_size
    require(size <= 1024 * 1024, '查询术语库超过1MiB上限')
    ledger.charge('read_bytes', size)
    try:
        # A hard read bound also protects against a concurrent growing file.
        with file.open('rb') as stream:
            raw = stream.read(1024 * 1024 + 1)
        require(len(raw) <= 1024 * 1024 and len(raw) == size, '查询术语库读取期间发生变化')
        value = json.loads(raw.decode('utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise QueryError('VALIDATION', '查询术语库不可读或JSON无效') from exc
    object_fields(value, {'schema_version', 'entries'})
    require(type(value['schema_version']) is int and value['schema_version'] == 1, '查询术语库版本无效')
    require(isinstance(value['entries'], list) and len(value['entries']) <= 2000, '查询术语条目数量无效')
    ids = set()
    for item in value['entries']:
        object_fields(item, {'id', 'domain', 'zh', 'en', 'aliases', 'related', 'sources', 'status'})
        for key in ('id', 'domain'):
            texts([item[key]], key)
        require(item['id'] not in ids, '查询术语库ID重复')
        ids.add(item['id'])
        require(item['status'] in {'active', 'disabled'}, '查询术语库状态无效')
        for key in ('zh', 'en', 'aliases', 'related', 'sources'):
            texts(item[key], key)
        require(bool(item['zh'] or item['en'] or item['aliases']), '查询术语缺少名称')
        require(item['status'] != 'active' or bool(item['sources']), '已启用查询术语必须有出处')
    return value['entries'], {'status': 'loaded', 'path': 'retrieval/query-terms.json',
                              'sha256': hashlib.sha256(raw).hexdigest()}


def build(root, ledger, raw):
    import retrieval
    original = raw['question']
    protected = texts(raw.get('protected_terms', []), 'protected_terms')
    # This conservative syntax check covers common version/model/numeric tokens;
    # units, negation and semantic relationships still need caller review.
    numeric = numeric_tokens(original)
    protected = list(dict.fromkeys(protected + numeric))
    require(all(preserves(original, term) for term in protected), '保护项必须来自原查询')
    language = raw.get('corpus_language', 'unknown')
    require(language in {'zh', 'en', 'mixed', 'unknown'}, '语料语言无效')
    reason = raw.get('language_reason', '')
    require(isinstance(reason, str) and len(reason) <= 12000, '语言选择依据无效')
    domains = texts(raw.get('query_domains', []), 'query_domains', 20)
    supplied = raw.get('query_variants', [])
    require(isinstance(supplied, list) and len(supplied) <= 3, '最多提供3条查询变体（总数含原查询）')
    original_language = 'zh' if re.search('[\u4e00-\u9fff]', original) else 'en' if re.search('[A-Za-z]', original) else 'other'
    variants = [{'id': 'original', 'language': original_language,
                 'question': original, 'lexical_terms': list(raw['keywords']) or retrieval.tokens(original)[:32]}]
    ids = {'original'}
    for item in supplied:
        object_fields(item, {'id', 'language', 'question', 'lexical_terms'})
        texts([item['id']], 'query_variant.id')
        require(isinstance(item['question'], str) and item['question'].strip() and len(item['question']) <= 12000,
                '查询变体语句无效')
        require(item['language'] in {'zh', 'en', 'other'}, '查询变体语言无效')
        terms = texts(item['lexical_terms'], 'lexical_terms', 32)
        require(bool(terms), '查询变体需要紧凑词法词项')
        require(all(preserves(item['question'], term) for term in protected), '查询变体丢失保护项，请修正译文')
        require(set(numeric_tokens(item['question'])) == set(numeric), '查询变体增加或改变数值/型号，请修正译文')
        same = next((v for v in variants if ' '.join(v['question'].casefold().split()) ==
                     ' '.join(item['question'].casefold().split())), None)
        if same is not None:
            same['lexical_terms'] = list(dict.fromkeys(same['lexical_terms'] + terms))[:32]
            continue
        require(item['id'] not in ids, '查询变体ID重复或使用保留ID original')
        ids.add(item['id'])
        variants.append(deepcopy(item))
    require(len(variants) <= 3, '去重后总查询变体最多3条（含原查询）')
    entries, trace = dictionary(root, ledger)
    matched, related = [], []
    # Match against the unexpanded plan exactly once, not newly appended terms.
    seed = '\n'.join(v['question'] + '\n' + '\n'.join(v['lexical_terms']) for v in variants)
    for entry in entries:
        family = entry['zh'] + entry['en'] + entry['aliases']
        if entry['status'] != 'active' or entry['domain'] not in ['general', *domains] or not any(
                contains(seed, term) for term in family):
            continue
        require(len(matched) < 16, '查询术语匹配超过16条，请缩小领域或查询')
        matched.append(deepcopy(entry))
        related.extend(entry['related'])
        for variant in variants:
            # Keep language routes distinct; caller terms and original aliases
            # remain literal, while natural dense sentences are never expanded.
            language_terms = entry.get(variant['language'], family)
            variant['lexical_terms'] = list(dict.fromkeys(variant['lexical_terms'] + language_terms + entry['aliases']))
    for variant in variants:
        variant['lexical_terms'] = list(dict.fromkeys(protected + variant['lexical_terms']))
        require(len(variant['lexical_terms']) <= 64, '扩展词项超过64项，请缩小查询')
    related = list(dict.fromkeys(related))
    require(len(related) <= 32, '关联词项超过32项，请缩小查询')
    return {'variants': variants, 'protected_terms': protected, 'corpus_language': language,
            'language_reason': reason, 'query_domains': domains, 'dictionary': trace,
            'matched_entries': matched, 'related_terms': related, 'condition_check': 'pending',
            'english_query_present': any(v['language'] == 'en' for v in variants),
            'language_decision_by': 'caller', 'translation_validation': 'literal_protection_only'}


def routes(plan):
    plan_id = digest(plan)
    # Identity keeps the literal input; tokenizing a MEM/model-like ID would
    # destroy exact lookup. Run it once rather than once per paraphrase.
    yield {'id': 'original:identity', 'variant_id': 'original', 'language': plan['variants'][0]['language'],
           'kind': 'identity', 'channel': 'identity', 'question': plan['variants'][0]['question'],
           'keywords': [], 'weight': 1.0, 'query_plan_id': plan_id}
    counts = Counter(v['language'] for v in plan['variants'])
    for variant in plan['variants']:
        for channel in ('lexical', 'dense'):
            yield {'id': variant['id'] + ':' + channel, 'variant_id': variant['id'],
                   'language': variant['language'], 'kind': 'equivalent', 'channel': channel,
                   'question': variant['question'] if channel == 'dense' else '',
                   'keywords': [] if channel == 'dense' else variant['lexical_terms'],
                   'weight': 1.0 / counts[variant['language']], 'query_plan_id': plan_id}
    if plan['related_terms']:
        yield {'id': 'related:lexical', 'variant_id': 'related', 'language': 'mixed',
               'kind': 'related', 'channel': 'lexical', 'question': '',
               'keywords': list(dict.fromkeys(plan['protected_terms'] + plan['related_terms'])),
               'weight': 0.25, 'query_plan_id': plan_id}


def fuse(batches):
    """One vote per fixed record per route; preserve every distinct hit origin."""
    merged = {}
    for route, candidates in batches:
        seen = set()
        for rank, candidate in enumerate(candidates, 1):
            key = digest(candidate['refs'][0])
            if key in seen:
                continue
            seen.add(key)
            row = merged.setdefault(key, {**deepcopy(candidate), 'hits': [], 'channels': [],
                                          'query_sources': [], 'fusion_score': 0.0})
            row['fusion_score'] += route['weight'] / (60 + rank)
            # Resolve full inputs through coverage.query_plan + variant/channel;
            # repeating a 12k question for every hit would inflate both storage
            # and the caller's context without adding provenance.
            row['query_sources'].append({**{field: route[field] for field in SOURCE_FIELDS}, 'rank': rank})
            row['channels'] = list(dict.fromkeys(row['channels'] + candidate['channels']))
            for hit in candidate.get('hits', []):
                sourced = {**deepcopy(hit), 'query_source': route['id'], 'query_plan_id': route['query_plan_id']}
                if sourced not in row['hits']:
                    row['hits'].append(sourced)
    return sorted(merged.values(), key=lambda row: (-row['fusion_score'], digest(row['refs'][0])))
