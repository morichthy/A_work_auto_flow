"""版本化工作台接口与受控静态资源。旧证据接口保持独立兼容。"""
import hashlib
import json
import mimetypes
from pathlib import Path
from urllib.parse import parse_qs
import evidence as e
from .analysis import export_summary

ASSETS = Path(__file__).resolve().parents[2] / 'ui/workbench-assets'
# __file__ 在 scripts/workbench_app；parents[2] 为 automation。


def asset_manifest():
    path = ASSETS / 'asset-manifest.json'
    if not path.exists():
        raise ValueError('工作台预构建资源缺失；开发者运行 npm run build，使用者重新下载完整版本')
    manifest = e.read(path)
    if manifest.get('api_version') != 1:
        raise ValueError('工作台资源/API 版本不兼容，请安装同一完整版本')
    return manifest


def asset(route):
    manifest = asset_manifest()
    relative = 'index.html' if not route else route
    if relative not in manifest['files']:
        raise ValueError('资源不在发布清单')
    path = ASSETS / relative
    if path.resolve() != path or not path.is_file():
        raise ValueError('资源缺失或路径被重定向')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest['files'][relative]:
        raise ValueError('资源指纹与发布清单不同')
    return raw, mimetypes.guess_type(path.name)[0] or 'application/octet-stream'


def get(service, route, query):
    args = parse_qs(query)
    one = lambda key, default='': args.get(key, [default])[0]
    if route == 'settings':
        from workspace_settings import read
        return read(service.root)
    if route == 'representations/definitions':
        from material_query.api import dispatch
        return dispatch(service.materials, 'definitions', {k: v[0] for k, v in args.items()})
    if route.startswith('materials/'):
        from material_query.api import dispatch
        if route not in {'materials/capabilities', 'materials/definitions'}:
            from material_query.coordinator import failure
            from material_query.validation import QueryError
            return failure(QueryError('VALIDATION', '此材料动作需要POST JSON'))
        return dispatch(service.materials, route[len('materials/'):], {k: v[0] for k, v in args.items()})
    if route.startswith('memory/'):
        from memory.api import dispatch
        from memory.service import MemoryService
        action = route[len('memory/'):]
        if action not in {'inspect', 'list-owners', 'history', 'document', 'figure', 'resume', 'associations-view'}:
            from memory.errors import MemoryError
            raise MemoryError('INVALID_ARGUMENT', '此记忆动作需要 POST JSON')
        request = {key: values[0] for key, values in args.items()}
        for key in ('revision', 'offset', 'limit', 'budget', 'figure_index'):
            if key in request:
                request[key] = int(request[key])
        return dispatch(MemoryService(service.root), action, request)
    if route == 'capabilities':
        return {'api_version': 1, 'build': asset_manifest()['source_fingerprint'],
                'graph_ready': service.graph is not None, 'synthetic': (service.root / 'synthetic-marker.json').exists(),
                'features': ['relations', 'keywords', 'clusters', 'candidates', 'export'],
                'semantic_configured': __import__('retrieval').config(service.root)['vector_store'].get('provider') == 'qdrant-local'}
    if route == 'graph':
        return service.view({'center': one('center'), 'hops': int(one('hops', '1')), 'query': one('query'),
                             'offset': int(one('offset', '0')), 'candidates': one('candidates') == 'true',
                             'excluded': args.get('excluded', []), 'types': args.get('types', []), 'kinds': args.get('kinds', []), 'levels': args.get('levels', [])})
    if route == 'catalog':
        graph = service.require_graph()
        return {'schema_version': 1, 'fingerprint': graph['fingerprint'], 'generated_at': graph['generated_at'],
                'nodes': graph['nodes'], 'edges': graph['edges'], 'coverage': graph['coverage'], 'errors': graph['errors']}
    if route == 'preview':
        return service.preview(one('id'), one('fingerprint'))
    if route == 'jobs':
        return {'jobs': service.jobs.list()}
    if route == 'view':
        return service.store.read('view', {})
    if route == 'candidates':
        return {'candidates': service.candidates()}
    if route == 'analysis':
        return service.store.read('analysis', {})
    if route == 'freshness':
        return {'changed_files': service.changed_files(), 'full_check': service.freshness_result,
                'note': '快速检查已知文件；新增/移除登记通过完整版本检查发现'}
    if route == 'clusters':
        return service.store.read('clusters', {})
    raise ValueError('未知 API')


def post(service, route, data):
    if route in {'reading-notes/recent', 'reading-notes/snapshot'}:
        from . import reading_notes
        return (reading_notes.recent if route.endswith('/recent') else reading_notes.snapshot)(service, data)
    if route in {'evidence/search', 'evidence/detail'}:
        from . import evidence_browser
        return (evidence_browser.search if route.endswith('/search') else evidence_browser.detail)(service, data)
    if route == 'settings':
        # 使用同一个CAS接口；HTTP处理器继续负责本机Origin/Host/token校验。
        from workspace_settings import update
        return update(service.root, data)
    if route == 'representations/inspect':
        from material_query.api import dispatch
        return dispatch(service.materials, 'inspect', data)
    if route.startswith('materials/'):
        from material_query.api import dispatch
        return dispatch(service.materials, route[len('materials/'):], data)
    if route.startswith('memory/'):
        from memory.api import dispatch
        from memory.service import MemoryService
        return dispatch(MemoryService(service.root), route[len('memory/'):], data)
    if not isinstance(data, dict):
        raise ValueError('请求必须为 JSON 对象')
    if route == 'jobs':
        return service.request_job(data)
    if route == 'cancel' and set(data) == {'id'}:
        return service.jobs.cancel(data['id'])
    if route == 'graph':
        return service.view(data)
    if route == 'export' and set(data) <= {'selection', 'question'}:
        return export_summary(service.view(data.get('selection')), data.get('question', ''))
    if route == 'view':
        return service.save_view(data)
    if route == 'clusters':
        # Worker 结果只能作为本机派生聚类；成员和输入版本必须来自当前投影。
        graph = service.require_graph()
        ids = {n['id'] for n in graph['nodes']}
        if data.get('fingerprint') != graph['fingerprint'] or not isinstance(data.get('clusters'), list):
            raise ValueError('聚类版本已过期或格式无效')
        for group in data['clusters']:
            if not isinstance(group, dict) or not isinstance(group.get('members'), list) or set(group['members']) - ids:
                raise ValueError('聚类包含未知材料')
        return service.store.write('clusters', data)
    if route == 'candidate':
        return service.save_candidate(data)
    if route == 'resolve' and set(data) == {'id', 'status', 'actor', 'note'}:
        return service.resolve_candidate(data['id'], data['status'], data['actor'], data['note'])
    raise ValueError('未知动作或字段')
