"""完成当前可变 Run 元数据；旧 Run 与旧 memory 提交不修改。"""
import json
from pathlib import Path
from datetime import datetime, timezone
path = Path(__file__).with_name('run.json')
value = json.loads(path.read_text(encoding='utf-8-sig'))
assert value['run_id'] == 'RUN-20260917T021448Z-BC1AAF379A2C'
value.update(status='completed', started_at=value['created_at'], ended_at=datetime.now(timezone.utc).isoformat(),
    question='阅读知识正文、分类型证据及图片是否正确展示，旧工作区升级后数据是否保留？',
    keywords=['reading note', 'evidence detail', 'inline citations', 'registered image'],
    conclusion='本轮六项修复及相关回归通过；实际浮点r9 HEAD不变，完整文稿与4图可读。详见RESULTS.md。',
    limitations=['科学结论和业务检索收益未复核；软件、合成AI及图片字节核验分别记录。',
                 '未做第二物理机验收；未发布。',
                 '历史无定位引用未臆造；旧规范报告r7差异已盘点，未整体同步。'])
path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
