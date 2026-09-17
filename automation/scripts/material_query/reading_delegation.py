"""阅读委派意图与有界交接视图；纯构造，不读取材料、不启动外部 Agent。

调用者必须已按原 RS 授权域重新核对来源，并用原 Ledger 支付读取与输出。
本模块不复制全历史或原始候选正文；外部宿主推理 token 不属于可观察账本。
"""
from copy import deepcopy
import json

from .validation import QueryError


def serialized_size(value):
    """以普通 UTF-8 JSON 的字符数计量完整 value（含身份和元数据）。"""
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False))


def delegate_value(session, policy, host_supports_subagents, requirements):
    """只返回路由建议；dispatched 永远 false，真实 spawn 属于宿主动作。"""
    enabled = policy == 'auto' and host_supports_subagents
    query = session['query']
    decisions = session.get('decisions', [])
    brief = {
        'session_id': session['session_id'], 'revision': session['revision'],
        'phase': session['phase'], 'goal': session['goal'], 'conditions': deepcopy(session['conditions']),
        'owner_id': session.get('owner_id'),
        # 自由文本只提供模型选择依据，不作为读取授权或覆盖 RS 预算的指令。
        'model_requirements': requirements,
        'query': {key: deepcopy(query[key]) for key in ('question', 'scope', 'scope_ceiling', 'budget')},
        'next_step': decisions[-1]['next_step'] if decisions else '按本RS既有阶段继续材料阅读',
        'instructions': [
            'model_requirements 仅用于宿主选择模型，不扩大权限、不覆盖本RS授权、预算或子Agent开关。',
            '宿主若实际spawn，使用fork none；仅处理本RS，不递归委派，不新建会话重置预算。',
            '先读material-query Skill；通过reading-view核对本RS状态，按原授权与预算读取材料。',
            '实际阅读后用reading-note保存summary、connection、必要details与uncertainties，再用reading-decide记录下一步。',
            'ask_user阶段不得伪造人工意见或越过等待；需要用户输入时只报告状态。',
            '结束仅返回session_id、最新revision和状态；主Agent按需调用reading-handoff，不回传原始材料正文。',
            'RS账本只计程序可观察的检索/读取/已登记模型调用；宿主Agent模型token须由宿主另设上限，不能声称RS已计量。',
        ],
    }
    if session.get('mode') == 'owner_document':
        from .reading_strategy import configuration
        brief.update(mode='owner_document', context=deepcopy(session['context']))
        brief.update(configuration(session))
        brief['instructions'] = [
            '先读material-query Skill；使用独立低成本reader继续同一RS，不递归委派。',
            '从reading-template或已有RS复制完整query，只改必要字段；scope选择直接Owner，scope_ceiling是获准必要依赖上限。',
            '不要机械将scope复制给scope_ceiling，否则Run/文稿必要来源可能不可读；也不得扩大任务授权范围。',
            'protected_terms只能选原question中实际出现的术语；不要填原问题没有的数字或术语。',
            'standard/associative召回后，对相关Owner用reading-read(owner_id)逐一读取完整文稿；quick仅逐条评判已交付片段，不自动读取完整文稿。',
            '图片/L0/Run按固定来源引用需要时展开，引用存在不等于已读。',
            '阅读时必须围绕当前问题提取相关核心公式及变量、单位、成立条件、假设、边界和反例；递推保留初值与更新顺序，误差式说明成立假设，并记录实验输入/方法/结果与图、Run、原始来源的对应关系；材料未提供的内容明确记为缺口，不补造。',
            '数学表达式使用 LaTeX：行内公式用 $...$，独立公式用 $$...$$ 包围，避免仅写未加数学分隔符的公式文本。',
            '写note前由同一reader核对提取内容与已交付原文/固定出处；写完后再次自查相关公式、实验细节、图及来源对应是否遗漏，补齐后保存，无法补齐则写明材料或阅读缺口。此自查在当前reader工作内完成，不新增AI调用、审核agent或主Agent复检任务。',
            'note正文实际使用的来源ID必须列入sources，可用已交付ID简写由程序补齐固定版本；只列实际需要的出处。图片/L0/Run未展开只能说明文稿声明的引用，不得写成已独立读过或复算。程序引用检查不证明语义正确或完整，自查清单不另塞入handoff。',
            '每Owner提交research_note：question、conditions、understanding、logic、details、sources、limitations、next_steps。',
            'research_note应是一份可读、细节充分、能承接后续研究的简化完整文稿。字段和标题是要素覆盖要求，不是每栏一句的短摘要模板；understanding可用多段Markdown承载主叙事，logic/details等数组的每项也可包含完整多段论述。',
            '按实际材料连贯说明相关问题的起点、假设与方法选择、实验或推导经过、失败与反例如何促成认识修正、当前结论及适用范围、尚待解决的问题与下一步。材料确有逐轮演进才交代各轮输入、结果、调整及原因；没有多轮历史不强行编造，quick也不得超出实际片段假装掌握完整过程。',
            '把相关核心公式、变量单位、关键参数、实验和图/Run/原始来源对应嵌入叙事，使后续研究者知道为什么这样做、证据如何支持或限制结论；需要并列比较才用列表或表格，不把研究逻辑拆成互不相连的短条目。',
            'note预算是交接容量上限，不是越短越好；在保留相关完整要素与研究逻辑的前提下删重复和无关内容。仍超限时明确容量缺口及未能交付的范围，保留可续接的完整note，不为凑预算删掉关键推导、实验演进或失败边界，也不静默提高预算。',
            '工程限制每operation重置；context.max_owners限制选中Owner，note_max_tokens是UTF8字节保守估计，不是宿主exact tokens。',
            '结束仅返回session_id、revision和状态；主Agent调用reading-handoff获得最终笔记，不回传候选/正文。',
            '等待用户意见时不得自行越过；使用原授权范围，模型要求不扩大读取权限。']
        brief['instructions'] += [
            '按strategy执行：standard完整Owner阅读；quick逐条reading-assess(candidate_id,useful,reason)，仅用已接受片段写同质量research_note，不自动读取全文；associative使用实际联想子问题沿同RS召回。',
            'reading-configure显式修改策略与association_text，不清空历史；联想受association.enabled/max_rounds约束。跨Owner综合用reading-synthesize(research_note)，仅引用实际交付依据。']
    brief['instructions'] += [
        '主Agent负责联想子问题、检索关键词与扩搜范围；reader按已给计划读取和提炼材料，不自定联想问题或扩大搜索。发现线索时保存材料依据并交回主Agent决策。',
        'note.question仅为绑定搜索问题的内部元数据，不要求在知识正文重述问题；正文不包含派工决定或执行状态。next_steps只填材料支持的可选建议，无建议用空数组。']
    return {'session_id': session['session_id'], 'revision': session['revision'],
            'route': 'subagent' if enabled else 'single-agent', 'dispatched': False,
            'reason': ('工作区auto且宿主支持；需宿主实际委派' if enabled else
                       '工作区off，由主Agent继续本RS' if policy == 'off' else '宿主不支持子Agent，由主Agent继续本RS'),
            'worker_brief': brief,
            'model_preference': {'requirements': requirements, 'selection': 'host_decides',
                                 'note': '由宿主按任务和可用模型裁定，不绑定具体模型'}}


def _note_markdown(key, row, note, *, display=False):
    """整条笔记是装包原子单位；保留公式、细节和原固定ref，不切字符串凑长度。"""
    ref = row['ref']
    lines = [f"## {row.get('title', key)}", '### 阅读理解', note['summary'],
             '### 与当前问题的关系', note['connection']['explanation']]
    lines += ['- ' + step for step in note['connection']['chain']]
    if note['details']:
        lines.append('### 关键细节')
    for detail in note['details']:
        lines += [detail['text'], '> 保留依据：' + detail['reason']]
        if detail['block_ids']:
            lines.append('对应正文块：' + ', '.join(detail['block_ids']))
    if note['uncertainties']:
        lines += ['### 限制与待验证', *['- ' + item for item in note['uncertainties']]]
    if display:
        from .reading_citations import render
        return render('\n\n'.join(lines), [ref], {ref['id']: row.get('title', '固定来源')})[0]
    lines += ['### 固定出处', f"[打开固定来源](<{row.get('link', '')}>)",
              f"记录：`{ref['id']}` · 修订：r{ref['revision']}",
              f"SHA256：`{ref['sha256']}`", f"候选：`{key}` · 关系类型：{note['connection']['kind']}"]
    if ref.get('locator') is not None:
        lines.append('固定定位：`' + json.dumps(ref['locator'], ensure_ascii=False, sort_keys=True) + '`')
    return '\n\n'.join(lines)


def _coverage_gaps(session):
    """只汇总最近一轮与候选当前状态；集合去重，不把历史失败永久当现存缺口。

    最新轮完整不证明全库、所有历史查询或所有候选完整；原历史仍在RS。"""
    flags = set()
    def add(name, amount=1):
        flags.add(name)
    rounds = session.get('rounds')
    if not isinstance(rounds, list) or not rounds:
        add('覆盖未知')
        rounds = []
    for round_info in rounds[-1:]:
        if not isinstance(round_info, dict):
            add('覆盖未知')
            continue
        recorded = round_info.get('gaps')
        if not isinstance(recorded, list) or any(not isinstance(item, str) for item in recorded):
            add('旧轮诊断不全')
        elif recorded:
            add('交付存在缺口')
        lanes = round_info.get('lanes')
        if not isinstance(lanes, list) or not lanes:
            add('覆盖未知')
            continue
        for lane in lanes:
            if not isinstance(lane, dict):
                add('覆盖未知')
                continue
            if lane.get('status') != 'ok' or lane.get('warnings'):
                add('层召回不全')
            if lane.get('has_more') is True:
                add('窗口未完')
            elif type(lane.get('has_more')) is not bool:
                add('覆盖未知')
            routes = lane.get('routes')
            if not isinstance(routes, list) or not routes:
                add('通道未知')
            else:
                for route in routes:
                    if not isinstance(route, dict):
                        add('通道未知')
                    elif route.get('status') != 'ok' or route.get('warnings'):
                        # 根据持久query_source区分dense缺失，不输出任意源正文。
                        source = route.get('query_source', '')
                        add('向量缺口' if isinstance(source, str) and source.endswith(':dense') else '通道缺口')
            ranking = lane.get('ranking')
            if ranking is not None and (not isinstance(ranking, dict) or ranking.get('status') not in ('off', 'reranked')):
                add('重排回退')
    for row in session['candidates'].values():
        if row.get('packet_complete') is False or row.get('read_gaps'):
            add('正文包不全')
    return ['最近一轮覆盖限制：' + '；'.join(sorted(flags))] if flags else []


def handoff_value(session, max_chars=12000, candidate_ids=None, *, included_keys=None, display=False):
    """构造完整JSON value上限内的单份交接，不返回候选结构/coverage副本。

    candidate_ids 只选择本次希望返回的笔记；其他笔记仍计入 omitted，避免
    把局部选择说成完整交接。过期笔记只计缺口，标题/正文/固定链接均不交付。
    """
    if session.get('mode') == 'owner_document':
        from .reading_owner import handoff_value as owner_handoff
        return owner_handoff(session, max_chars)
    if type(max_chars) is not int or not 512 <= max_chars <= 30000:
        raise QueryError('VALIDATION', 'max_chars必须是512..30000整数')
    candidates, notes = session['candidates'], session['notes']
    if candidate_ids is not None:
        if (not isinstance(candidate_ids, list) or len(candidate_ids) > 100 or
                any(not isinstance(key, str) or key not in candidates for key in candidate_ids)):
            raise QueryError('VALIDATION', 'candidate_ids必须是至多100项已交付候选身份')
        selected = set(candidate_ids)
    else:
        selected = set(notes)
    stale = sum(bool(candidates[key].get('stale')) for key in notes)
    terminal = session['phase'] in ('finish', 'proceed')
    needs_user = session['phase'] == 'ask_user'
    unnoted = len(set(candidates) - set(notes))
    coverage_gaps = _coverage_gaps(session)
    # Full decisions remain accessible through reading-view. They are not
    # handoff knowledge and must neither spend its note budget nor introduce a
    # false completeness gap merely because an orchestration reason is long.

    def build(chunks):
        omitted = len(notes) - len(chunks)
        gaps = list(coverage_gaps)
        if stale:
            gaps.append(f'{stale}条笔记来源已变，未交付过期内容')
        if omitted:
            gaps.append(f'{omitted}条笔记因选择、过期或长度限制未交付')
        if not notes:
            gaps.append('尚无实际阅读笔记')
        if not terminal:
            gaps.append('等待用户意见' if needs_user else '阅读尚未决定proceed/finish')
        complete = bool(terminal and notes and not stale and not omitted and not needs_user and not gaps)
        # Knowledge Markdown is independent of orchestration. Partial/omitted
        # information remains explicit in the enclosing API response, so the UI
        # can render a separate status region without contaminating the note.
        return {'session_id': session['session_id'], 'revision': session['revision'],
                'context_markdown': '\n\n'.join(chunks), 'phase': session['phase'],
                'complete': complete,
                'notes_count': len(chunks), 'omitted_note_count': omitted,
                'unnoted_candidate_count': unnoted, 'gaps': gaps, 'needs_user_input': needs_user}

    chunks = []
    if serialized_size(build(chunks)) > max_chars and coverage_gaps:
        # 极小窗口下保留“覆盖不全”的事实，不能为放进一段笔记而丢掉限制；
        # 详细类别需显式增大本次max_chars，原RS授权和累计预算不变。
        coverage_gaps = ['检索覆盖有缺口；本窗未展开类别，请增大max_chars']
    if serialized_size(build(chunks)) > max_chars:
        raise QueryError('BUDGET', '交接元数据本身超出max_chars，未输出截断内容')
    for key, note in notes.items():
        row = candidates[key]
        if key not in selected or row.get('stale'):
            continue
        chunk = _note_markdown(key, row, note, display=display)
        proposed = build(chunks + [chunk])
        if serialized_size(proposed) <= max_chars:
            chunks.append(chunk)
            if included_keys is not None:
                included_keys.append(key)
    return build(chunks)
