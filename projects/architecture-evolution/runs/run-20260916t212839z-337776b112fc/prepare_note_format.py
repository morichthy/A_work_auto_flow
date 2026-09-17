"""为用户指出的现有note准备纯数学排版修订；不直接写RS或科学记录。

只替换已人工阅读确认的数学片段。请求经正常reading-note授权/CAS/来源核验，
失败即保留原版。来源、实验数字、文字结论及限制逐字保留。
"""
from copy import deepcopy
import difflib
import json
from pathlib import Path
import re

RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[3]
sid = 'RS-a8f812d7-d8f9-4862-8e8f-932cc5649d3b'
owner = 'RES-FLOATING-POINT-SUMMATION'
session = json.loads((ROOT/'.local/reading-sessions'/sid/'HEAD.json').read_text(encoding='utf-8'))
assert session['revision'] == 8, '请重新审查并发变化，不覆盖其他修订'
original = session['owner_notes'][owner]
fields = ('question', 'conditions', 'understanding', 'logic', 'details', 'sources', 'limitations', 'next_steps')
note = {key: deepcopy(original[key]) for key in fields}
replacements = {
    's_0=c_0=0': r's_0=c_0=0',
    's_0=0': r's_0=0',
    's_i=fl(s_{i-1}+x_i)': r's_i=\operatorname{fl}(s_{i-1}+x_i)',
    'S_hat=s_n': r'\widehat S=s_n',
    'y_i=fl(x_i-c_{i-1})': r'y_i=\operatorname{fl}(x_i-c_{i-1})',
    't_i=fl(s_{i-1}+y_i)': r't_i=\operatorname{fl}(s_{i-1}+y_i)',
    'c_i=fl(fl(t_i-s_{i-1})-y_i)': r'c_i=\operatorname{fl}(\operatorname{fl}(t_i-s_{i-1})-y_i)',
    's_i=t_i': r's_i=t_i',
    'e_abs=|Fraction(S_hat)-S_ref|': r'e_{\mathrm{abs}}=|\operatorname{Fraction}(\widehat S)-S_{\mathrm{ref}}|',
    'S_ref=sum Fraction(x_i)': r'S_{\mathrm{ref}}=\sum \operatorname{Fraction}(x_i)',
    'e_abs=0': r'e_{\mathrm{abs}}=0',
    '[10^16,1,-10^16]': r'[10^{16},1,-10^{16}]',
    'y=fl(-10^16-(-1))': r'y=\operatorname{fl}(-10^{16}-(-1))',
    'c=-1': r'c=-1',
    '-10^16': r'-10^{16}',
    'x_i': r'x_i', 's_i': r's_i', 'c_i': r'c_i', 'y_i': r'y_i',
}
# One pass with longest alternatives avoids wrapping variables inside a newly
# formatted equation a second time. This is a bounded migration, not a heuristic
# that tries to infer formulas in arbitrary Markdown.
pattern = re.compile('|'.join(re.escape(key) for key in sorted(replacements, key=len, reverse=True)))
def formatted(value):
    return pattern.sub(lambda match: '$'+replacements[match[0]]+'$', value)
note['understanding'] = formatted(note['understanding'])
for field in ('logic', 'details'):
    note[field] = [formatted(item) for item in note[field]]
assert note['sources'] == original['sources']
assert note['limitations'] == original['limitations']
request = {'session_id': sid, 'expected_revision': 8,
           'request_id': 'format-math-20260917-337776b112fc', 'owner_id': owner, 'research_note': note}
(RUN/'note-format-request.json').write_text(json.dumps(request, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
before = json.dumps({key:original[key] for key in fields}, ensure_ascii=False, indent=2)
after = json.dumps(note, ensure_ascii=False, indent=2)
(RUN/'note-format.diff').write_text('\n'.join(difflib.unified_diff(before.splitlines(), after.splitlines(), fromfile='r8', tofile='proposed-format-only'))+'\n', encoding='utf-8')
print('Prepared public CAS request; no canonical records written.')
