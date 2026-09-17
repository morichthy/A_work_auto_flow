"""共享证据导航读模型：只读业务元数据与选中记录，不依赖HTTP展示层。

搜索索引仅作定位。输出前核对当前Owner/记录敏感性和来源登记；文件原件
只检查登记与安全路径，不哈希、不读取。正式证据结论继续使用原强核验接口。
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

from manifest_discovery import manifests
from memory import owners, index
from memory.evidence_adapter import iter_refs
from memory.service import MemoryService
from memory.errors import MemoryError
from material_query.validation import QueryError
from material_query.budget import Ledger, DEFAULT_BUDGET
from material_query.reader import MeteredStore
from material_query.reading_citations import evidence_url


def workspace_id(root):
    return hashlib.sha256(str(Path(root).resolve()).casefold().encode('utf-8')).hexdigest()[:24]


def read_json(path, maximum=4 * 1024 * 1024):
    if path.stat().st_size > maximum:
        raise ValueError('元数据文件超过展示上限')
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    return value


def native_registration(raw, ref, kind):
    """工具登记表的身份在 tools 成员，不在整个 registry 根对象。

    只沿原索引的明确 id_field/id_value 精确选择，绝不对身份错误回退首项。
    普通业务卡仍核对根身份，保留损坏拒绝边界。
    """
    if kind == 'tool' and isinstance(raw.get('tools'),list):
        matches=[item for item in raw['tools'] if item.get('tool_id') == ref.get('id_value')]
        if len(matches)!=1: raise ValueError('工具登记身份不存在或重复')
        raw=matches[0]
    if ref.get('id_field') and raw.get(ref['id_field']) != ref.get('id_value'):
        raise ValueError('Owner登记身份与原卡不一致')
    return raw


class Catalog:
    """每次请求一个有界导航视图；从业务卡或索引登记定位Owner。"""
    def __init__(self, root, access=None, *, permission_metadata=False):
        self.root = Path(root).resolve()
        self.access = None if access is None else set(access)
        self.permission_metadata = permission_metadata
        self.owners, self.records, self.record_cache = {}, {}, {}
        self.warnings, self.record_paths, self.source_files = [], set(), set()
        self.store = MeteredStore(self.root, Ledger(DEFAULT_BUDGET))
        self.service = MemoryService(self.root)
        self.db = index.connect(self.root, create=False)
        # The shared manifest scanner excludes captures/caches and refuses
        # reparse points. Only named business cards are parsed here.
        for path in manifests(self.root, owners.CARDS):
            try:
                kind, key = owners.CARDS[path.name]
                raw = read_json(owners.safe_path(self.root, path.relative_to(self.root).as_posix()))
                oid = raw.get(key)
                if not isinstance(oid, str) or not oid:
                    raise ValueError('业务卡缺少稳定身份')
                self.add_owner(oid, kind, path.relative_to(self.root).as_posix(), raw)
            except (ValueError, OSError, MemoryError, QueryError):
                self.warnings.append('一份业务登记损坏或不可访问，已隔离；其他对象继续展示。')
        if self.db:
            for row in self.db.execute('SELECT owner_id,owner_type,native_ref FROM memory_owners'):
                if row['owner_id'] in self.owners:
                    continue
                try:
                    ref = json.loads(row['native_ref'])
                    path = owners.safe_path(self.root, ref['path'])
                    if not path.is_file():
                        raise ValueError('登记原对象不存在')
                    if path.suffix.lower() != '.json':
                        # Explicit adopted metadata only; never open originals.
                        raw = {'title': path.stem}
                    else:
                        raw = read_json(path)
                        raw = native_registration(raw,ref,row['owner_type'])
                    self.add_owner(row['owner_id'], row['owner_type'], ref['path'], raw)
                except (ValueError, OSError, MemoryError, QueryError):
                    self.warnings.append('一份索引Owner定位失效或登记损坏，已隔离。')
            for row in self.db.execute("SELECT * FROM memory_records WHERE entity_kind='record'"):
                self.records[row['record_id']] = dict(row)
        # Unindexed current records are discoverable from small manifests, not
        # by opening every commit or original source. Their bodies are read only
        # when a search actually requires metadata or a selected detail.
        for oid, owner in self.owners.items():
            try:
                _, manifest = self.store.head_manifest(owner)
            except (ValueError, OSError, MemoryError, QueryError):
                self.warnings.append('部分Owner记忆清单损坏，未将其作为有效证据展示。')
                continue
            if manifest:
                for rid, entry in manifest['record_heads'].items():
                    indexed = self.records.get(rid)
                    if indexed is None or indexed.get('content_hash') != entry['record_hash']:
                        # Stale search text must not suppress newly changed
                        # conclusions. Only this row falls back to current data.
                        self.records[rid] = {'record_id': rid, 'owner_id': oid, 'title': '', 'body': '', 'content_hash': entry['record_hash']}

    def close(self):
        if self.db:
            self.db.close()

    def add_owner(self, oid, kind, relative, raw):
        if oid in self.owners:
            raise ValueError('重复Owner身份')
        home = owners._home(kind, relative, oid)
        descriptor = owners.safe_path(self.root, home + '/owner.json')
        if descriptor.exists():
            saved = read_json(descriptor)
            if saved.get('owner_id') != oid or saved.get('memory_home') != home or saved.get('native_ref', {}).get('path') != relative:
                raise ValueError('Owner持久登记与原定位不一致')
        self.owners[oid] = {'owner_id': oid, 'owner_type': kind, 'native_ref': {'path': relative},
                            'memory_home': home, 'native_data': raw, 'title': raw.get('title') or raw.get('name') or oid}

    def owner(self, oid):
        owner = self.owners.get(oid)
        if not owner or self.access is not None and oid not in self.access or owner['native_data'].get('sensitivity') == 'restricted' or any(c.get('sensitivity') == 'restricted' for c in owner['native_data'].get('claims', [])):
            raise ValueError('对象不在当前可读范围')
        return owner

    def record(self, rid, revision=None):
        row = self.records.get(rid)
        if row is None:
            raise ValueError('记录身份不存在')
        owner = self.owner(row['owner_id'])
        key = (rid, revision)
        if key not in self.record_cache:
            if self.permission_metadata:
                # Snapshot display is explicitly not an evidence integrity
                # check. Inspect canonical access labels even when content hash
                # validation would reject an old scientific record. Missing or
                # malformed identity still fails closed; detail/handoff remain
                # strict and never use this path to return evidence bodies.
                _, manifest = self.store.head_manifest(owner)
                entry = None
                while manifest:
                    possible = manifest.get('record_heads', {}).get(rid)
                    if possible and (revision is None or possible['revision'] == revision):
                        entry = possible
                        break
                    parent = manifest['parent_commit_id']
                    manifest = self.store._manifest(owner, parent, manifest['parent_manifest_hash']) if parent else None
                if not entry:
                    raise ValueError('记录权限元数据缺失')
                record_path = self.store.path(owner, entry['path'])
                self.record_paths.add(record_path.relative_to(self.root).as_posix())
                value = read_json(record_path)
                if value.get('record_id') != rid or value.get('owner_id') != owner['owner_id']:
                    raise ValueError('记录权限元数据身份损坏')
                self.record_cache[key] = value
            else:
                self.record_cache[key] = self.store.read_record(owner, rid, revision)
        value = self.record_cache[key]
        if value.get('sensitivity') == 'restricted':
            raise ValueError('记录当前限制读取')
        if revision is not None:
            self.record(rid)
        return value

    def authorize(self, raw, seen=None):
        """只核访问闭包，不读原件。撤权在任何导航正文输出之前生效。"""
        seen = set() if seen is None else seen
        for ref in [*iter_refs(raw), *self.native_refs(raw)]:
            key = (ref['target_kind'], ref['target_id'], ref.get('revision'))
            if key in seen:
                continue
            seen.add(key)
            if len(seen) > 1000:
                raise ValueError('来源授权闭包超过展示上限')
            kind, tid = key[:2]
            if kind == 'file':
                self.service._file(ref)
                self.source_files.add(tid)
            elif kind == 'record':
                record = self.record(tid, ref.get('revision'))
                if not self.permission_metadata and ref.get('sha256') and record['record_hash'] != ref['sha256']:
                    raise ValueError('记录固定版本指纹不匹配')
                self.authorize({'sources': record.get('sources', []), 'payload': record.get('payload', {})}, seen)
            elif kind == 'owner':
                self.authorize(self.owner(tid)['native_data'], seen)
            elif kind == 'claim':
                matches = [o for o in self.owners.values() if any(c.get('claim_id') == tid for c in o['native_data'].get('claims', []))]
                if len(matches) != 1:
                    raise ValueError('结论引用暂不可安全定位')
                self.owner(matches[0]['owner_id'])
                self.authorize(matches[0]['native_data'], seen)

    def native_refs(self, raw):
        """旧Run显式dependencies/evidence_refs按已知身份解析，不读路径原件。"""
        if not isinstance(raw, dict):
            return []
        values = list(raw.get('dependencies', [])) + list(raw.get('evidence_refs', []))
        for claim in raw.get('claims', []):
            values.extend(claim.get('evidence_refs', []))
        registry_path = owners.safe_path(self.root, 'retrieval/sources.json')
        registry = read_json(registry_path) if values and registry_path.exists() else {'sources':[]}
        import retrieval
        refs = []
        for value in values:
            if not isinstance(value, dict) or 'target_kind' in value:
                continue
            target = value.get('target') or value.get('path')
            if not isinstance(target, str):
                continue
            if target in self.owners:
                kind, identity = 'owner', target
            elif target in self.records:
                kind, identity = 'record', target
            elif target.startswith('CLM-'):
                kind, identity = 'claim', target
            else:
                matches = [(source, source.get('source_id') or source.get('id') or retrieval.source_id((self.root/source['path']).resolve()))
                           for source in registry.get('sources', [])]
                matches = [(source, sid) for source, sid in matches if target == sid or target.replace('\\','/') == source['path'].replace('\\','/')]
                if len(matches) != 1:
                    self.warnings.append('部分旧式依赖没有已登记证据身份；仅显示声明，不读取未登记原件。')
                    continue
                kind, identity = 'file', matches[0][1]
            refs.append({'target_kind':kind, 'target_id':identity, 'revision':value.get('revision'),
                         'sha256':value.get('sha256'), 'locator':value.get('locator'), 'relation':value.get('relation','references')})
        return refs

    def guard(self):
        """授权元数据指纹：只含小型登记卡/HEAD，不含任何原件字节。"""
        paths = {'retrieval/sources.json'}
        paths.update(self.record_paths)
        for owner in self.owners.values():
            paths.update((owner['native_ref']['path'], owner['memory_home'] + '/HEAD.json', owner['memory_home'] + '/owner.json'))
        paths.update('registered:' + identity for identity in self.source_files)
        return {name: file_stamp(self.root, name) for name in sorted(paths)}


def file_stamp(root, name):
    if name.startswith('registered:'):
        # Existing registry ID, not a caller-supplied path. _file checks current
        # enabled/sensitivity and refuses external junctions, without hashing.
        path, _ = MemoryService(root)._file({'target_id': name[len('registered:'):]})
        stat = path.stat()
        return [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
    path = owners.safe_path(root, name)
    if not path.exists():
        return None
    stat = path.stat()
    return [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]


def summary(raw):
    values = [raw.get(key) for key in ('overview', 'summary', 'conclusion', 'description', 'objective', 'goal')]
    return '\n\n'.join(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False) for value in values if value)


def record_text(record):
    payload = record.get('payload', {})
    values = [summary(record), record.get('body_markdown', ''), summary(payload)]
    values.extend(block.get('markdown', '') for block in payload.get('blocks', []))
    return '\n\n'.join(value for value in values if value)


def render_content_citations(text, refs, titles):
    """已有正文 ID 可定位；只有 sources 的旧材料只能给文末参考文献。

    通用 note renderer 的“本节依据”是对整份 note 的声明，不能移植为
    历史记录的逐段证据位置。保留其固定编号/结构保护，但移除该附加声明。
    """
    from .reading_citations import render
    rendered, references = render(text, refs, titles)
    if references:
        marker = '\n\n本节依据：'
        start = rendered.rfind(marker)
        end = rendered.find('\n\n### 参考文献', start)
        if start >= 0 and end >= 0:
            rendered = rendered[:start] + rendered[end:]
    return rendered, references


def citation_sources(record):
    """结构装配边不是论据；只收正文声明的来源与块级 evidence_refs。"""
    payload = record.get('payload',{})
    content = {key:value for key,value in payload.items() if key not in {'section_refs','watch_refs','missing_refs'}}
    if isinstance(content.get('blocks'),list):
        content['blocks']=[{key:value for key,value in block.items() if not (key=='ref' and block.get('type') in {'unit','detail'})}
                           for block in content['blocks']]
    return list(iter_refs({'sources':record.get('sources',[]),'payload':content}))


def raster_media(catalog, ref):
    """选中图片才读取受控栅格字节；登记 ID 不是任意路径能力。

    固定图片实际核哈希，且读取前后重查登记权限与路径。SVG/HTML 不作为
    可执行媒体返回。普通文字详情仍不读取原件；图片预算为单张 8 MiB。
    """
    import base64
    path, registration = catalog.service._file(ref)
    bound_owner = registration.get('owner_id')
    if bound_owner:
        catalog.owner(bound_owner)
    elif catalog.access is not None:
        raise ValueError('图片登记未绑定授权Owner，不能在窄授权域单独展示')
    if not path.resolve().is_relative_to(catalog.root):
        raise ValueError('图片必须为工作区内受控附件')
    expected = ref.get('sha256') or registration.get('sha256')
    if not expected:
        raise ValueError('图片没有固定指纹，不能展示为已验证原件')
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('图片超过 8 MiB 展示上限')
    with path.open('rb') as stream:
        raw = stream.read(8 * 1024 * 1024 + 1)
    mime = ('image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else
            'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else
            'image/webp' if raw[:4] == b'RIFF' and raw[8:12] == b'WEBP' else None)
    if len(raw) > 8 * 1024 * 1024 or mime is None or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('图片格式或固定指纹不匹配')
    after, current = catalog.service._file(ref)
    if after != path or current != registration:
        raise ValueError('图片登记读取期间发生变化')
    return {'type':'image','data_url':'data:'+mime+';base64,'+base64.b64encode(raw).decode('ascii'), 'sha256':expected}


_PAYLOAD_LABELS = {'overview':'整体概览','summary':'摘要','conclusion':'结论','recommendation':'建议',
    'applicability':'适用条件','limitations':'限制','events':'研究经过','steps':'过程',
    'purpose':'目的','audience':'读者','scope':'范围','question':'问题','answer':'认识',
    'method':'方法','result':'结果','conditions':'条件','next_steps':'可选的下一步建议',
    'occurred_at':'发生时间','content':'内容','description':'说明','rationale':'依据',
    'mechanism':'机制','tradeoffs':'权衡','boundary':'边界','insights':'认识',
    'retrieval_description':'检索说明','applicable':'适用条件','key_findings':'主要认识',
    'not_applicable':'不适用条件','unit_type':'技术单元类型','methods':'方法','results':'结果',
    'current_stage':'当前阶段','open_questions':'未解决问题','claims':'结论声明','action':'行动',
    'observation':'观察','decision':'认识变化','failure':'失败与反例','occurred_at':'发生时间'}


def readable_value(value):
    """将已保存内容结构展开成可读段落，不把 ref/机器状态伪作正文。"""
    if isinstance(value, str): return value
    if isinstance(value, list): return '\n\n'.join(readable_value(item) for item in value)
    if isinstance(value, dict):
        if 'target_kind' in value: return ''
        return '\n\n'.join(('**'+_PAYLOAD_LABELS.get(key,key)+'**\n\n'+readable_value(item))
                            for key,item in value.items() if item and not key.endswith('_refs') and key not in {'ref','sources','figures','knowledge_facets'})
    return str(value) if value is not None else ''


def record_content(catalog, record, seen=None):
    """按固定 document→section→detail 引用装配，不用最新修订替代旧引用。

    只沿显式内容边展开；普通 sources 是证据关系，不意味着把所有上游全文
    嵌入。循环/超深文稿拒绝，防止引用图无界扩展。
    """
    seen = set() if seen is None else set(seen)
    identity = (record.get('record_id'), record.get('revision'))
    if identity in seen or len(seen) >= 32: raise ValueError('文稿内容引用循环或超过深度上限')
    seen.add(identity)
    payload, sections = record.get('payload', {}), []
    if hasattr(catalog,'content_records'):
        catalog.content_records[identity] = record
    pieces = [record.get('body_markdown','')]
    def fixed(ref):
        child = catalog.record(ref['target_id'],ref.get('revision'))
        if ref.get('sha256') and child['record_hash'] != ref['sha256']: raise ValueError('文稿固定内容指纹不匹配')
        catalog.authorize(child)
        return child
    if record.get('kind') == 'document':
        for ref in payload.get('section_refs',[]):
            child = fixed(ref)
            text, child_sections = record_content(catalog,child,seen)
            sections.append(dict(id=child['record_id'],title=child['title'],kind=child['kind'],level=child.get('level'),
                                 content_markdown=text,record=deepcopy(child),references=list(iter_refs(child)),images=[],sections=child_sections))
            pieces.append('## '+child['title']+'\n\n'+text)
    for block in payload.get('blocks',[]):
        if block.get('type') in {'detail','unit'} and block.get('ref'):
            child=deepcopy(fixed(block['ref']))
            if block.get('type') == 'unit':
                from memory.technical_units import select_blocks
                selected,_ = select_blocks(child,block.get('block_ids'))
                child['payload']['blocks']=selected
            text,nested=record_content(catalog,child,seen)
            sections.append(dict(id=child['record_id'],title=child['title'],kind=child['kind'],level=child.get('level'),
                                 content_markdown=text,record=deepcopy(child),references=list(iter_refs(child)),images=[],sections=nested))
            pieces.append('### '+child['title']+'\n\n'+text)
        else:
            text=block.get('markdown','')
            # Explicit per-block evidence_refs are genuine saved locations.
            refs=list(iter_refs({'sources':block.get('evidence_refs',[])}))
            if refs:
                text += '\n\n本段依据：'+' '.join(ref['target_id'] for ref in refs)
            pieces.append(text)
    excluded={'blocks','section_refs','common_refs','watch_refs','missing_refs','figures','knowledge_facets','document_type','section_key','role','title',
              'retrieval_description','unit_type'}
    for key,value in payload.items():
        if key in excluded or key.endswith('_refs') or not value: continue
        # Overview/narrative/experience store knowledge in payload, not always
        # body_markdown. Preserve each field rather than choosing one summary.
        rendered=readable_value(value)
        if rendered and rendered not in pieces: pieces.append('## '+_PAYLOAD_LABELS.get(key,key)+'\n\n'+rendered)
    text='\n\n'.join(piece for piece in pieces if piece).strip()
    if hasattr(catalog,'content_images'):
        import re
        # Each record has its own figure:0 namespace. Allocate response-local
        # slots at the leaf, before embedding its text into a parent document.
        slots={}
        for number,figure in enumerate(payload.get('figures',[])):
            key=(identity,number)
            if key not in catalog.figure_slots:
                image=raster_media(catalog,figure['ref'])
                slot=len(catalog.content_images)
                catalog.figure_slots[key]=slot
                catalog.content_images.append(dict(index=slot,caption=figure.get('caption',''),ref=figure['ref'],record_id=record.get('record_id'),**image))
            slots[number]=catalog.figure_slots[key]
        text=re.sub(r'(!\[[^\]]*\]\(figure:)(\d+)(\))',lambda match:match[1]+str(slots.get(int(match[2]),int(match[2])))+match[3],text) if slots else text
    return text, sections


def metadata_item(identity, owner, kind, title, body, tags=None, updated=None):
    return dict(id=identity, owner_id=owner, kind=kind, title=title, summary=body[:1200],
                tags=tags or [], updated_at=updated, url=evidence_url({'id': identity}))


def search(service, raw):
    if set(raw) - {'query', 'limit', 'offset'}:
        raise ValueError('未知证据搜索字段')
    query, limit, offset = raw.get('query', ''), raw.get('limit', 20), raw.get('offset', 0)
    if not isinstance(query, str) or len(query) > 1000 or type(limit) is not int or not 1 <= limit <= 50 or type(offset) is not int or offset < 0:
        raise ValueError('证据搜索参数无效')
    catalog = Catalog(service.root, service.materials.access_owner_ids)
    try:
        matches, warnings = [], catalog.warnings
        terms = query.casefold().split()
        for oid in catalog.owners:
            try:
                owner = catalog.owner(oid)
                data = owner['native_data']
                body = summary(data)
                if all(term in (oid+' '+owner['title']+' '+body).casefold() for term in terms):
                    catalog.authorize(data)
                    matches.append(metadata_item(oid, oid, owner['owner_type'], owner['title'], body, data.get('keywords', []), data.get('updated_at')))
                for claim in data.get('claims', []):
                    cid = claim.get('claim_id')
                    if not isinstance(cid, str):
                        continue
                    claim_text = claim.get('statement', '') + '\n\n' + summary(claim)
                    title = claim.get('title') or claim.get('statement', '')[:120] or '已登记结论'
                    if all(term in (cid+' '+title+' '+claim_text).casefold() for term in terms):
                        catalog.authorize(data)
                        matches.append(metadata_item(cid, oid, 'claim', title, claim_text, claim.get('keywords', []), data.get('updated_at')))
            except (ValueError, OSError, MemoryError, QueryError):
                continue
        for rid, indexed in catalog.records.items():
            # Indexed text is a candidate filter only. Selected metadata is
            # resolved from canonical current records before disclosure.
            text = rid+' '+indexed.get('title', '')+' '+indexed.get('body', '')+' '+indexed.get('payload', '')
            if indexed.get('title') and not all(term in text.casefold() for term in terms):
                continue
            try:
                record = catalog.record(rid)
                catalog.authorize(record)
                body = record_text(record)
                if not all(term in (rid+' '+record['title']+' '+body).casefold() for term in terms):
                    continue
                matches.append(metadata_item(rid, record['owner_id'], record['kind'], record['title'], body, record.get('keywords', []), record.get('updated_at')))
            except (ValueError, OSError, MemoryError, QueryError):
                warnings.append('部分记忆记录损坏或不可访问，未返回其正文。')
                continue
        matches.sort(key=lambda row: (row['id'].casefold() == query.casefold(), row.get('updated_at') or '', row['id']), reverse=True)
        selected = matches[offset:offset+limit]
        return {'workspace_id': workspace_id(service.root), 'items': selected, 'total': len(matches),
                'next_offset': offset+len(selected) if offset+len(selected) < len(matches) else None,
                'verification': 'metadata_only', 'warnings': list(dict.fromkeys(warnings))}
    finally:
        catalog.close()


def detail(service, raw):
    if set(raw) - {'id', 'revision', 'sha256', 'locator'} or not isinstance(raw.get('id'), str):
        raise ValueError('证据详情需要合法ID')
    catalog = Catalog(service.root, service.materials.access_owner_ids)
    try:
        identity = raw['id']
        registry_path = owners.safe_path(service.root, 'retrieval/sources.json')
        registry = read_json(registry_path) if registry_path.exists() else {'sources': []}
        import retrieval
        registered = [source for source in registry.get('sources', []) if
                      (source.get('source_id') or source.get('id') or retrieval.source_id((service.root / source['path']).resolve())) == identity]
        source_warning = []
        sections, images, media = [], [], None
        if registered:
            if len(registered) != 1:
                raise ValueError('来源ID重复，不能选择固定证据')
            source_path, data = catalog.service._file({'target_id': identity})
            if raw.get('revision') is not None:
                raise ValueError('登记原件没有可回读的修订号')
            if raw.get('sha256') and data.get('sha256') and raw['sha256'] != data['sha256']:
                raise ValueError('来源登记指纹与请求不同；未回退当前版')
            oid, kind = data.get('owner_id'), 'file'
            if oid:
                catalog.owner(oid)
            elif catalog.access is not None:
                # Source IDs do not grant a new trusted Owner scope.
                raise ValueError('此来源未绑定可验证Owner，窄授权域不能独立展开')
            title = data.get('title') or data.get('name') or Path(data['path']).name
            body = summary(data) or '该来源仅有登记信息；本次未读取原件内容。'
            if raw.get('locator'):
                body += '\n\n固定定位：' + raw['locator']
            ref = {'kind': 'file', 'id': identity, 'revision': None, 'sha256': raw.get('sha256') or data.get('sha256'), 'locator': raw.get('locator')}
            source_warning = ['仅显示已登记原件元数据；原始文件内容和固定哈希尚未重新核验。']
            if source_path.suffix.lower() in {'.png','.jpg','.jpeg','.webp'}:
                media = raster_media(catalog, {'target_id':identity,'sha256':ref['sha256']})
                media['caption'] = title
                body = summary(data) or '已展示所选登记图片，原始图片字节与固定 SHA256 一致。'
                source_warning = ['所选图片已核对固定 SHA256；未重新复核科学结论。']
        elif identity in catalog.records:
            data = catalog.record(identity, raw.get('revision'))
            catalog.authorize(data)
            ref = {'kind': 'record', 'id': identity, 'revision': data['revision'], 'sha256': data['record_hash'], 'locator': raw.get('locator')}
            if raw.get('sha256') and raw['sha256'] != ref['sha256']:
                raise ValueError('指定证据指纹与固定记录不一致，未回退当前版')
            content_record = deepcopy(data)
            blocks = content_record.get('payload', {}).get('blocks', [])
            locator = raw.get('locator') or ''
            if locator.startswith('block:'):
                blocks = [block for block in blocks if block['block_id'] == locator[6:]]
                if not blocks:
                    raise ValueError('指定正文块不存在')
                content_record['body_markdown'] = ''
                content_record['payload'] = {'blocks':blocks}
            catalog.content_records, catalog.content_images, catalog.figure_slots = {}, [], {}
            body, sections = record_content(catalog, content_record)
            images = catalog.content_images
            oid, kind, title = data['owner_id'], data['kind'], data['title']
        elif identity in catalog.owners:
            owner = catalog.owner(identity)
            data = owner['native_data']
            catalog.authorize(data)
            if raw.get('revision') is not None:
                raise ValueError('native Owner不支持伪造历史修订')
            # Native files are mutable metadata. Their canonical raw-JSON hash
            # is not substituted for a requested file hash; reject uncertainty.
            if raw.get('sha256'):
                import evidence
                native_path = owners.safe_path(service.root, owner['native_ref']['path'])
                if native_path.suffix.lower() != '.json':
                    raise ValueError('此原始文档指纹需强证据接口核验，轻量详情不读取原件')
                if raw['sha256'] not in {evidence.fingerprint(data), hashlib.sha256(native_path.read_bytes()).hexdigest()}:
                    raise ValueError('Owner元数据已变化，固定引用不可用')
            oid, kind, title = identity, owner['owner_type'], owner['title']
            body = summary(data)
            for field in ('method', 'methods', 'result', 'results', 'limitations'):
                if data.get(field):
                    body += '\n\n## '+field+'\n\n'+(data[field] if isinstance(data[field], str) else json.dumps(data[field], ensure_ascii=False, indent=2))
            ref = {'kind': 'owner', 'id': identity, 'revision': None, 'sha256': raw.get('sha256'), 'locator': raw.get('locator')}
        else:
            claims = [(owner, claim) for owner in catalog.owners.values() for claim in owner['native_data'].get('claims', []) if claim.get('claim_id') == identity]
            if len(claims) != 1:
                raise ValueError('证据ID不存在或当前不可访问')
            owner, data = claims[0]
            catalog.owner(owner['owner_id']); catalog.authorize(owner['native_data'])
            import evidence
            if raw.get('sha256') and raw['sha256'] != evidence.fingerprint(data):
                raise ValueError('结论固定指纹已变化，未回退当前版')
            oid, kind, title = owner['owner_id'], 'claim', data.get('title') or data.get('statement', identity)
            body = data.get('statement', '') + '\n\n' + summary(data)
            ref = {'kind':'claim', 'id':identity, 'revision':None, 'sha256':evidence.fingerprint(data), 'locator':raw.get('locator')}
        links = []
        content_records = list(getattr(catalog,'content_records',{}).values())
        all_refs=[*iter_refs(data), *catalog.native_refs(data)]
        for child in content_records: all_refs.extend(iter_refs(child))
        unique_refs={json.dumps(item,sort_keys=True):item for item in all_refs}
        for item in unique_refs.values():
            fixed = {'kind': item['target_kind'], 'id': item['target_id'], 'revision': item.get('revision'), 'sha256': item.get('sha256'), 'locator': item.get('locator')}
            title_ref = catalog.owners.get(fixed['id'], {}).get('title') or catalog.records.get(fixed['id'], {}).get('title')
            if fixed['kind'] == 'record':
                # Authorization already followed this selected reference. Read
                # its exact canonical title even when the derived search row is
                # absent/stale; never borrow a current title for an old revision.
                title_ref = catalog.record(fixed['id'],fixed.get('revision'))['title']
            if not title_ref:
                source = next((source for source in registry.get('sources', []) if (source.get('source_id') or source.get('id')) == fixed['id']), None)
                title_ref = (source.get('title') or source.get('name') or Path(source['path']).name) if source else '固定来源'
            links.append({'id': fixed['id'], 'title': title_ref, 'relation': item.get('relation', 'references'), 'url': evidence_url(fixed), 'ref': fixed})
        if oid and identity != oid:
            links.insert(0, {'id': oid, 'title': catalog.owner(oid)['title'], 'relation': 'belongs_to', 'url': evidence_url({'id': oid})})
        impacts = []
        for rid, row in catalog.records.items():
            # The derived payload is enough to discover reverse links; each
            # matching container is authorized canonically before its title leaks.
            haystack = row.get('payload', '') + row.get('source_ref', '')
            # A record's top-level sources need not occur in indexed payload.
            # Reverse navigation reads bounded canonical metadata only, never
            # full EvidenceGraph/state or original source files.
            try:
                target = catalog.record(rid)
                catalog.authorize(target)
                for item in [*iter_refs(target), *catalog.native_refs(target)]:
                    if item['target_id'] == identity:
                        impacts.append({'id': rid, 'title': target['title'], 'relation': item.get('relation', 'references'), 'url': evidence_url({'id': rid})})
                        break
            except (ValueError, OSError, MemoryError, QueryError):
                continue
        for candidate in catalog.owners.values():
            if candidate['owner_id'] == identity:
                continue
            if any(item['target_id'] == identity for item in [*iter_refs(candidate['native_data']), *catalog.native_refs(candidate['native_data'])]):
                try:
                    catalog.owner(candidate['owner_id']); catalog.authorize(candidate['native_data'])
                    impacts.append({'id': candidate['owner_id'], 'title': candidate['title'], 'relation': 'references', 'url': evidence_url({'id': candidate['owner_id']})})
                except (ValueError, OSError, MemoryError, QueryError):
                    continue
        context = {key: deepcopy(data[key]) for key in ('level', 'validity', 'review', 'conditions', 'record_reason', 'execution_status', 'status', 'inputs', 'parameters', 'owner_id','outputs','artifacts','results','limitations','environment','method','methods') if key in data}
        context['owner_summary'] = summary(catalog.owner(oid)['native_data']) if oid else ''
        if kind == 'file':
            context['source_registration'] = {key:data[key] for key in ('path','enabled','sensitivity','sha256','type') if key in data}
        supporting = {(item['target_kind'],item['target_id'],item.get('revision'),item.get('sha256'),item.get('locator')) for record in [data,*content_records] for item in citation_sources(record)}
        fixed_sources = [item['ref'] for item in links if item.get('ref') and
                         (item['ref']['kind'],item['ref']['id'],item['ref'].get('revision'),item['ref'].get('sha256'),item['ref'].get('locator')) in supporting]
        body, citation_references = render_content_citations(body.strip() or '此对象暂未保存可展示的结论或正文；参见元数据、引用与影响关系。', fixed_sources,
            {item['id']: item['title'] for item in links})
        def decorate(rows):
            for section in rows:
                section['images']=images
                section['content_markdown']=render_content_citations(section['content_markdown'],fixed_sources,{item['id']:item['title'] for item in links})[0]
                decorate(section.get('sections',[]))
        decorate(sections)
        return dict(workspace_id=workspace_id(service.root), id=identity, owner_id=oid, kind=kind, title=title,
                    content_markdown=body, tags=data.get('keywords', []), context=context, citation_references=citation_references,
                    references=links, impacts=impacts, fixed_ref=ref, verification='metadata_only',
                    record=deepcopy(data) if identity in catalog.records else None, level=data.get('level'),
                    sections=sections, images=images, media=media,
                    # Unrelated stale index entries are search inventory issues,
                    # not a defect in the selected evidence. Never attach global
                    # catalog warnings to an otherwise valid local detail.
                    warnings=list(dict.fromkeys(source_warning + ['已检查当前访问边界；未重新复核科学结论。'])))
    finally:
        catalog.close()
