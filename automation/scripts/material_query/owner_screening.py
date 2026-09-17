"""Build small, complementary evidence packets from Owner discovery hits.

This module is deliberately storage agnostic.  It only selects among hits that
the discovery adapter has already authorized and pinned to canonical refs.
"""
from copy import deepcopy
import re

from .validation import QueryError
from .wire import digest


DEFAULTS = {'regular_windows': 3, 'max_windows': 4, 'batch_owners': 10}


def settings(raw=None):
    value = deepcopy(DEFAULTS if raw is None else raw)
    if not isinstance(value, dict) or set(value) != set(DEFAULTS):
        raise QueryError('VALIDATION', 'screening只接受regular_windows、max_windows、batch_owners')
    for key, minimum, maximum in [('regular_windows', 1, 4), ('max_windows', 1, 4),
                                  ('batch_owners', 1, 100)]:
        if type(value[key]) is not int or not minimum <= value[key] <= maximum:
            raise QueryError('VALIDATION', key + '超出允许范围')
    if value['regular_windows'] > value['max_windows']:
        raise QueryError('VALIDATION', 'regular_windows不能超过max_windows')
    return value


def _text_key(value):
    """Collapse presentation whitespace only; semantic near-duplicates stay distinct."""
    return re.sub(r'\s+', ' ', value).strip().casefold()


def _ref_key(ref):
    return digest({key: ref.get(key) for key in ('kind', 'id', 'revision', 'sha256', 'locator')})


def _merge_exact(hits):
    merged = []
    by_text = {}
    for position, source in enumerate(hits):
        hit = deepcopy(source)
        text = hit.get('text', '')
        if not isinstance(text, str) or not text.strip():
            continue
        hit.setdefault('_position', position)
        hit.setdefault('refs', [hit['fixed_ref']] if hit.get('fixed_ref') else [])
        hit.setdefault('channels', [hit['channel']] if hit.get('channel') else [])
        hit.setdefault('matched_protected_terms', [])
        key = _text_key(text)
        if key not in by_text:
            by_text[key] = hit
            merged.append(hit)
            continue
        target = by_text[key]
        target['refs'] = list({_ref_key(ref): ref for ref in target['refs'] + hit['refs']}.values())
        target['channels'] = list(dict.fromkeys(target['channels'] + hit['channels']))
        target['matched_protected_terms'] = list(dict.fromkeys(
            target['matched_protected_terms'] + hit['matched_protected_terms']))
        target.setdefault('merged_projection_ids', []).append(hit.get('projection_id'))
    return merged


def _record_ids(hit):
    return {ref.get('id') for ref in hit.get('refs', []) if ref.get('id')}


def build(candidate, raw_settings=None):
    """Select a core hit then windows that add route, record/location or constraints."""
    options = settings(raw_settings)
    hits = _merge_exact(candidate.get('hits', []))
    if not hits:
        raise QueryError('SOURCE_MISSING', 'Owner没有可交付的发现命中')
    ordered = sorted(hits, key=lambda hit: (-float(hit.get('relevance_score', hit.get('score', 0.0)) or 0.0),
                                            hit['_position'], hit.get('projection_id', '')))
    chosen = [ordered.pop(0)]
    while ordered and len(chosen) < options['regular_windows']:
        channels = {channel for hit in chosen for channel in hit.get('channels', [])}
        records = {record for hit in chosen for record in _record_ids(hit)}
        locations = {(ref.get('id'), hit.get('locator')) for hit in chosen for ref in hit.get('refs', [])}

        def gain(hit):
            new_channels = len(set(hit.get('channels', [])) - channels)
            new_records = len(_record_ids(hit) - records)
            new_locations = len({(ref.get('id'), hit.get('locator')) for ref in hit.get('refs', [])} - locations)
            protected = bool(hit.get('matched_protected_terms'))
            return (3 * protected + 2 * new_channels + new_records + new_locations,
                    float(hit.get('relevance_score', hit.get('score', 0.0)) or 0.0),
                    -hit['_position'])

        best = max(ordered, key=gain)
        if gain(best)[0] <= 0:
            break
        chosen.append(best)
        ordered.remove(best)
    # A regular packet stays compact.  The hard limit is reserved for an
    # additional protected-condition hit that would otherwise be absent.
    if len(chosen) < options['max_windows'] and not any(hit.get('matched_protected_terms') for hit in chosen):
        protected = next((hit for hit in ordered if hit.get('matched_protected_terms')), None)
        if protected is not None:
            chosen.append(protected)

    windows = []
    for hit in chosen[:options['max_windows']]:
        windows.append({key: deepcopy(hit.get(key)) for key in (
            'projection_id', 'text', 'refs', 'source_level', 'source_kind', 'channels', 'locator',
            'matched_protected_terms') if hit.get(key) not in (None, [], '')})
    complete = len(hits) == 1 and len(windows) == 1 and hits[0].get('source_level') == 'L4' and bool(
        hits[0].get('complete_source'))
    gaps = [] if complete else ['筛选包只覆盖实际发现命中；尚未完整阅读Owner']
    packet = {'owner_id': candidate['owner_id'], 'title': candidate.get('title'),
              'overview': candidate.get('overview'), 'windows': windows,
              'coverage': {'complete': complete, 'gaps': gaps}}
    packet['packet_digest'] = digest(packet)
    return packet


def build_batch(candidates, raw_settings=None):
    options = settings(raw_settings)
    return [build(candidate, options) for candidate in candidates[:options['batch_owners']]]
