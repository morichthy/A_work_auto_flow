"""工作区唯一可编辑设置：严格完整快照、内容 CAS 和有界只读缓存。

公开 read(root) 不补种文件；update(root, request) 只写 workspace-settings.json。
工程默认值来自实际查询预算，阅读上下文另有Owner数和笔记估算token。调用者拿到深拷贝，
因此不能通过修改返回对象污染进程缓存。设置只是后续请求的默认值，不修改既有
会话额度，也不代表对原件/来源的授权。
"""
from collections import OrderedDict
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import threading

from material_query.budget import DEFAULT_BUDGET, SERVER_LIMITS
from memory.errors import MemoryError


_NAME = 'workspace-settings.json'
_MAX_BYTES = 64 * 1024
_MAX_ROOTS = 64
_DEFAULT_SUBAGENT_REQUIREMENTS = '优先使用低成本、较低能力的可用模型，采用低推理深度；须能完成材料检索、完整阅读和结构化笔记。'
_CACHE = OrderedDict()
# 所有根共用短临界区，避免每个访问过的路径永久残留一个锁对象。跨进程互斥
# 另由 O_EXCL 文件锁负责；不以年龄猜测锁是否失效，不擅自抢占旧锁。
_LOCK = threading.RLock()


def _defaults():
    return {
        'collaboration': {'subagents': 'auto', 'subagent_requirements': _DEFAULT_SUBAGENT_REQUIREMENTS},
        'materials': {'result_limit': 20, 'budget': asdict(DEFAULT_BUDGET)},
        'reading': {'strategy': 'standard', 'association': {'enabled': True, 'max_rounds': 3},
                    'result_limit': 10, 'context': {'max_owners': 10, 'note_max_tokens': 6000},
                    # 筛选包在Owner级冻结，常规窗口数只决定首批交付，硬上限
                    # 防止单个Owner的多条命中重新挤占整批上下文。
                    'screening': {'regular_windows': 3, 'max_windows': 4, 'batch_owners': 10},
                    # CE逐窗口处理。超长文本围绕实际命中截窗，禁止因一个
                    # 条目超长把整批回退到原排序。
                    'reranking': {'mode': 'auto', 'candidate_limit': 30, 'window_tokens': 512,
                                  'overflow_policy': 'hit_centered_per_window'},
                    'budget': asdict(replace(DEFAULT_BUDGET, candidates=1000, model_calls=20,
                        model_tokens=65536, model_input_tokens=65536, rerank_items=100))},
    }


def _invalid(message):
    raise MemoryError('INVALID_ARGUMENT', message)


def _fields(value, names, location):
    if not isinstance(value, dict) or set(value) != set(names):
        _invalid(location + '必须提供完整且无未知字段的对象')


def _validate(settings):
    """严格校验完整配置；磁盘旧格式仅在 _read 的兼容入口补新增字段。"""
    _fields(settings, ('collaboration', 'materials', 'reading'), 'settings')
    _fields(settings['collaboration'], ('subagents', 'subagent_requirements'), 'collaboration')
    if settings['collaboration']['subagents'] not in ('auto', 'off'):
        _invalid('subagents 只允许 auto/off')
    requirements = settings['collaboration']['subagent_requirements']
    # strip 仅用于非空及长度校验；保存原文，避免悄悄改写用户的自由文本偏好。
    if not isinstance(requirements, str) or not 1 <= len(requirements.strip()) <= 2000:
        _invalid('subagent_requirements 必须是去除首尾空白后 1..2000 字符的文本')
    limits = asdict(SERVER_LIMITS)
    for section in ('materials', 'reading'):
        value = settings[section]
        _fields(value, ('result_limit', 'budget', 'reranking', 'context', 'screening', 'strategy', 'association') if section == 'reading'
                else ('result_limit', 'budget'), section)
        if type(value['result_limit']) is not int or not 1 <= value['result_limit'] <= 100:
            _invalid(section + '.result_limit 必须是 1..100 整数')
        _fields(value['budget'], limits, section + '.budget')
        for name, maximum in limits.items():
            amount = value['budget'][name]
            minimum = 1 if name == 'wall_ms' else 0
            if type(amount) is not int or not minimum <= amount <= maximum:
                _invalid(section + '.budget.' + name + ' 超出允许的整数范围')
    if settings['reading']['strategy'] not in ('standard', 'associative', 'quick'):
        _invalid('reading.strategy 只允许 standard/associative/quick')
    association = settings['reading']['association']
    _fields(association, ('enabled', 'max_rounds'), 'reading.association')
    if type(association['enabled']) is not bool:
        _invalid('reading.association.enabled 必须是布尔值')
    if type(association['max_rounds']) is not int or not 1 <= association['max_rounds'] <= 20:
        _invalid('reading.association.max_rounds 必须是 1..20 整数')
    # Owner 数与最终笔记估算 token 是阅读上下文预算；旧 budget 仍单独保护工程资源。
    context = settings['reading']['context']
    _fields(context, ('max_owners', 'note_max_tokens'), 'reading.context')
    for name, minimum, maximum in (('max_owners', 1, 100), ('note_max_tokens', 512, 50000)):
        if type(context[name]) is not int or not minimum <= context[name] <= maximum:
            _invalid('reading.context.' + name + f' 必须是 {minimum}..{maximum} 整数')
    screening = settings['reading']['screening']
    _fields(screening, ('regular_windows', 'max_windows', 'batch_owners'), 'reading.screening')
    for name, minimum, maximum in (('regular_windows', 1, 4), ('max_windows', 1, 4),
                                   ('batch_owners', 1, 100)):
        if type(screening[name]) is not int or not minimum <= screening[name] <= maximum:
            _invalid('reading.screening.' + name + f' 必须是 {minimum}..{maximum} 整数')
    if screening['regular_windows'] > screening['max_windows']:
        _invalid('每个Owner常规窗口数不能大于窗口硬上限')
    ranking = settings['reading']['reranking']
    _fields(ranking, ('mode', 'candidate_limit', 'window_tokens', 'overflow_policy'), 'reading.reranking')
    if ranking['mode'] not in ('off', 'auto', 'required'):
        _invalid('reading.reranking.mode 无效')
    limit = ranking['candidate_limit']
    if type(limit) is not int or not 1 <= limit <= 100:
        _invalid('candidate_limit 必须是 1..100 整数')
    if ranking['mode'] != 'off' and limit < settings['reading']['result_limit']:
        _invalid('重排候选窗不能小于阅读交付数量')
    if type(ranking['window_tokens']) is not int or not 64 <= ranking['window_tokens'] <= 512:
        _invalid('reading.reranking.window_tokens 必须是 64..512 整数')
    if ranking['overflow_policy'] != 'hit_centered_per_window':
        _invalid('reading.reranking.overflow_policy 只允许 hit_centered_per_window')
    return deepcopy(settings)


def _root(root):
    """不创建根目录；拒绝传入经链接/联接重定向的工作区路径。"""
    try:
        raw = Path(os.path.abspath(os.fspath(root)))
        if raw.resolve() != raw or not raw.is_dir():
            _invalid('工作区必须是已存在且未重定向的目录')
        return raw
    except (OSError, TypeError, ValueError) as exc:
        raise MemoryError('INVALID_ARGUMENT', '工作区路径不可用') from exc


def _signature(value):
    return (value.st_mtime_ns, value.st_ctime_ns, value.st_size, value.st_ino, value.st_dev)


def _state(path):
    """每次缓存命中仍核对路径类型；stat 的五元签名不只依赖可回写的 mtime。"""
    try:
        value = path.lstat()
    except FileNotFoundError:
        return None
    if (not stat.S_ISREG(value.st_mode) or stat.S_ISLNK(value.st_mode)
            or getattr(value, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
            or path.resolve() != path):
        _invalid('设置路径必须是普通文件，禁止目录、链接或重定向')
    if value.st_size > _MAX_BYTES:
        _invalid('设置文件超过 64 KiB')
    return _signature(value)


def _snapshot(raw, settings):
    return {'revision': hashlib.sha256(raw).hexdigest(), 'settings': settings,
            'defaults': _defaults(), 'limits': asdict(SERVER_LIMITS)}


def _remember(root, signature, value):
    _CACHE[root] = (signature, value)
    _CACHE.move_to_end(root)
    while len(_CACHE) > _MAX_ROOTS:
        _CACHE.popitem(last=False)
    return deepcopy(value)


def _unique_fields(pairs):
    """重复 JSON 键同样拒绝，避免不同解析器对同一设置产生不同解释。"""
    value = {}
    for key, item in pairs:
        if key in value:
            _invalid('设置 JSON 含重复字段')
        value[key] = item
    return value


def _read(root):
    path = root / _NAME
    # 原子替换可与读取同时发生。打开前后验证签名，只缓存一次稳定读取；持续
    # 外部改写则明确报告冲突，不用旧缓存遮盖损坏或返回拼接中的半份配置。
    for _ in range(3):
        signature = _state(path)
        cached = _CACHE.get(root)
        if cached is not None and cached[0] == signature:
            _CACHE.move_to_end(root)
            return deepcopy(cached[1])
        if signature is None:
            return _remember(root, None, _snapshot(b'', _defaults()))
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        try:
            with os.fdopen(os.open(path, flags), 'rb') as stream:
                opened = _signature(os.fstat(stream.fileno()))
                raw = stream.read(_MAX_BYTES + 1)
            # Windows CPython 的 CRT fstat 与路径 lstat 对 ctime（创建/变更
            # 时间）可能取不同来源。句柄比较使用 mtime/size/ino/dev，路径
            # 前后及缓存仍使用完整五元组，不能因此丢掉 ctime 失效判断。
            if opened[0:1] + opened[2:] != signature[0:1] + signature[2:] or _state(path) != signature:
                continue
        except FileNotFoundError:
            continue
        if len(raw) > _MAX_BYTES:
            _invalid('设置文件超过 64 KiB')
        try:
            payload = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_unique_fields)
        except (UnicodeError, ValueError, RecursionError) as exc:
            raise MemoryError('INVALID_ARGUMENT', '设置文件不是有效 UTF-8 JSON') from exc
        _fields(payload, ('schema_version', 'settings'), '设置文件')
        if type(payload['schema_version']) is not int or payload['schema_version'] != 1:
            _invalid('设置 schema_version 不支持')
        settings = payload['settings']
        # 兼容补齐仅作用于 schema-1 磁盘读取：旧 collaboration 恰好只有
        # subagents 时补新增默认。其余缺失/未知字段仍由完整校验拒绝；原字节
        # 和 CAS revision 不变。写请求不经过此路径，旧客户端不能遗漏偏好覆盖。
        if (isinstance(settings, dict) and isinstance(settings.get('collaboration'), dict)
                and set(settings['collaboration']) == {'subagents'}):
            settings = deepcopy(settings)
            settings['collaboration']['subagent_requirements'] = _DEFAULT_SUBAGENT_REQUIREMENTS
        # 旧 schema-1 只读补齐新增上下文设置，不改写自定义工程预算及磁盘/CAS。
        # 仅接受精确旧字段集合，避免借兼容入口掩盖损坏或未知字段。
        if (isinstance(settings, dict) and isinstance(settings.get('reading'), dict)
                and set(settings['reading']) in ({'result_limit', 'budget', 'reranking'},
                    {'result_limit', 'budget', 'reranking', 'strategy', 'association'},
                    {'result_limit', 'budget', 'reranking', 'screening', 'strategy', 'association'})):
            settings = deepcopy(settings)
            settings['reading']['context'] = _defaults()['reading']['context']
        # 三模式成对补齐，仅接受发布过的完整旧结构；缺半份新配置仍视为损坏。
        if (isinstance(settings, dict) and isinstance(settings.get('reading'), dict)
                and set(settings['reading']) in ({'result_limit', 'budget', 'reranking', 'context'},
                    {'result_limit', 'budget', 'reranking', 'context', 'screening'})):
            settings = deepcopy(settings)
            settings['reading']['strategy'] = 'standard'
            settings['reading']['association'] = _defaults()['reading']['association']
        # 2026-09 Owner发现设置只读迁移：仅接受上一版完整reading结构和
        # 精确旧reranking形状。内存补默认不改变原字节或CAS revision；写入
        # 仍必须发送完整新结构，避免旧客户端清除新策略。
        if (isinstance(settings, dict) and isinstance(settings.get('reading'), dict)
                and set(settings['reading']) == {'result_limit', 'budget', 'reranking', 'context',
                                                 'strategy', 'association'}
                and isinstance(settings['reading'].get('reranking'), dict)
                and set(settings['reading']['reranking']) == {'mode', 'candidate_limit'}):
            settings = deepcopy(settings)
            defaults = _defaults()['reading']
            settings['reading']['screening'] = defaults['screening']
            settings['reading']['reranking'].update({
                'window_tokens': defaults['reranking']['window_tokens'],
                'overflow_policy': defaults['reranking']['overflow_policy']})
        return _remember(root, signature, _snapshot(raw, _validate(settings)))
    raise MemoryError('VERSION_CONFLICT', '设置在读取期间持续变化，请重新读取')


def read(root):
    """只读完整设置快照；缺文件返回默认值及空字节内容 hash，不创建任何文件。"""
    with _LOCK:
        try:
            return _read(_root(root))
        except OSError as exc:
            raise MemoryError('INVALID_ARGUMENT', '无法读取工作区设置') from exc


def update(root, request):
    """以 expected_revision 原子保存完整设置，并返回与 read 相同的快照。

    写入锁覆盖 CAS、暂存和替换；临时文件与目标位于同一目录/卷。仅清理本次
    创建的锁和临时文件，旧锁即使没有活进程也返回 LOCKED，供人核实后处理。
    """
    _fields(request, ('expected_revision', 'settings'), '更新请求')
    revision = request['expected_revision']
    if not isinstance(revision, str) or len(revision) != 64 or any(c not in '0123456789abcdef' for c in revision):
        _invalid('expected_revision 必须是 read 返回的 SHA-256')
    settings = _validate(request['settings'])
    raw = (json.dumps({'schema_version': 1, 'settings': settings}, ensure_ascii=False,
                      sort_keys=True, indent=2) + '\n').encode('utf-8')
    if len(raw) > _MAX_BYTES:
        _invalid('设置文件超过 64 KiB')
    with _LOCK:
        root = _root(root)
        path, lock = root / _NAME, root / (_NAME + '.lock')
        descriptor, lock_signature, temporary = None, None, None
        try:
            try:
                descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                     getattr(os, 'O_NOFOLLOW', 0), 0o600)
            except FileExistsError as exc:
                raise MemoryError('LOCKED', '工作区设置正在更新，已有锁不会自动抢占') from exc
            lock_signature = _signature(lock.lstat())
            current = _read(root)
            if current['revision'] != revision:
                raise MemoryError('VERSION_CONFLICT', '工作区设置已变化，请重新读取后保存')
            previous_state = _state(path)
            fd, name = tempfile.mkstemp(prefix='.' + _NAME + '.', suffix='.tmp', dir=root)
            temporary = Path(name)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            # 不合作的外部编辑器不持本锁；替换前再检测可见变化。正常写入者
            # 由 O_EXCL 严格串行化；不能用失配的旧 expected_revision 覆盖新值。
            if _state(path) != previous_state:
                raise MemoryError('VERSION_CONFLICT', '工作区设置在保存期间变化')
            os.replace(temporary, path)
            temporary = None
            _CACHE.pop(root, None)
            return _read(root)
        except OSError as exc:
            raise MemoryError('INVALID_ARGUMENT', '工作区设置保存失败，未报告成功') from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            if lock_signature is not None:
                try:
                    # 若外部操作替换了锁，不能删除别人的新锁文件。
                    if _signature(lock.lstat()) == lock_signature:
                        lock.unlink()
                except FileNotFoundError:
                    pass
