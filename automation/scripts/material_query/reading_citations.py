"""统一阅读笔记引用展示；编号属于完整固定ref，不修改规范note字段。"""
from copy import deepcopy
import re
from urllib.parse import urlencode
from .wire import digest

# Also versions the derived Markdown envelope. Version 4 separates knowledge
# prose from workflow decisions; old display copies are rebuilt on selection.
FORMAT_VERSION = 4


def evidence_url(ref):
    query = {'id': ref.get('id', ref.get('target_id'))}
    for key in ('revision', 'sha256', 'locator'):
        if ref.get(key) is not None:
            query[key] = ref[key]
    return '#/evidence?' + urlencode(query)


def render(markdown, sources, titles=None, *, links=True):
    """仅替换普通叙述中的已知ID，代码、公式、已有链接和URL保持原样。

    同ID可能有多个块或修订；一次出现映射到全部匹配的编号，不把同ID
    错当成同一证据。参考文献保留机器字段，缺标题不猜研究结论。
    """
    titles = titles or {}
    refs = list({digest(ref): deepcopy(ref) for ref in sources}.values())
    references = [dict(number=n, ref=ref, title=titles.get(ref['id'], '固定来源 ' + str(n)), url=evidence_url(ref))
                  for n, ref in enumerate(refs, 1)]
    by_id = {}
    for item in references:
        by_id.setdefault(item['ref']['id'], []).append(item)
    # Protect existing Markdown structures before plain-prose substitutions.
    protected = r'(```[\s\S]*?```|`[^`\n]*`|\$\$[\s\S]*?\$\$|\$[^$\n]*\$|\\\[[\s\S]*?\\\]|\\\([^\n]*?\\\)|!?\[[^\]]*\]\([^\n]*?\)|https?://\S+)'
    parts = re.split(protected, markdown)
    if by_id:
        # A reader may write [MEM-ID] as an explicit source marker. Consume
        # that matched pair too; protected real links/code/math never enter here.
        pattern = re.compile(r'(?<![A-Za-z0-9_-])(\[)?(' + '|'.join(re.escape(k) for k in sorted(by_id, key=len, reverse=True)) + r')(?![A-Za-z0-9_-])(?(1)\])')
        for index in range(0, len(parts), 2):
            parts[index] = pattern.sub(lambda m: ''.join('[' + str(item['number']) + ']' + ('(' + item['url'] + ')' if links else '') for item in by_id[m[2]]), parts[index])
    text = ''.join(parts)
    if references:
        text += '\n\n本节依据：' + ' '.join('['+str(item['number'])+']'+('('+item['url']+')' if links else '') for item in references) + '。'
        text += '\n\n### 参考文献\n\n'
        for item in references:
            ref = item['ref']
            label = item['title'].replace('[', '（').replace(']', '）')
            text += f"[{item['number']}] " + (f"[{label}]({item['url']})" if links else label) + '\n\n'
    return text.rstrip(), references
