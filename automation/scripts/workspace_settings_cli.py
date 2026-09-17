"""工作区设置的程序入口：读、CAS保存和精简协作策略，不经过AI解析文件。"""
import json
from pathlib import Path

from memory.errors import MemoryError
import workspace_settings


def add_commands(subparsers):
    parser = subparsers.add_parser('workspace-settings', help='工作区默认检索预算与协作开关')
    actions = parser.add_subparsers(dest='settings_action', required=True)
    actions.add_parser('show', help='输出当前设置、revision、默认值和服务端上限')
    actions.add_parser('policy', help='输出精简协作策略，任务开始时读取一次')
    save = actions.add_parser('set', help='从JSON请求文件保存完整设置（必须包含expected_revision）')
    save.add_argument('--request', required=True, type=Path)


def execute(root, args):
    try:
        if args.settings_action == 'set':
            # 请求文件也受大小约束，防止误把材料正文作为配置载入。
            with args.request.open('rb') as handle:
                raw = handle.read(65537)
            if len(raw) > 65536:
                raise MemoryError('INVALID_ARGUMENT', '设置请求不能超过64 KiB')
            result = workspace_settings.update(root, json.loads(raw.decode('utf-8')))
        else:
            result = workspace_settings.read(root)
            if args.settings_action == 'policy':
                result = {'revision': result['revision'], **result['settings']['collaboration'],
                          'fallback': 'single-agent', 'host_capability_required': True}
        return result, 0
    except MemoryError as exc:
        return {'error': exc.as_dict()}, exc.exit_code
    except (OSError, ValueError) as exc:
        return {'error': {'code': 'INVALID_ARGUMENT', 'message': str(exc)}}, 2
