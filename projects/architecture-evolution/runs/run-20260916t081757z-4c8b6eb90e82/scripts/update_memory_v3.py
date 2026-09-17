"""续接已成功的unit批次；按章节契约合并同一技术单元的选中块。

v2第二批预检未提交，原失败请求另存保留。这里只修正该批草案，复用已成功
第一批及其固定引用，不改已登记脚本、旧记录或Run元数据。
"""
from copy import deepcopy
import importlib.util
from pathlib import Path

# 工作区Python以隔离模式运行，不把脚本目录隐式加入sys.path；显式加载同目录脚本。
spec = importlib.util.spec_from_file_location('capability_memory_workflow', Path(__file__).with_name('update_memory_v2.py'))
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)

original_batch = workflow.batch


def corrected_batch(service, key, changes):
    if key == '02-sections-overviews':
        changes = deepcopy(changes)
        blocks = changes['settings-section']['payload']['blocks']
        # section契约要求同一unit只出现一次，多个正文块用block_ids有序选择。
        changes['settings-section']['payload']['blocks'] = [
            blocks[0], blocks[2],
            {'type': 'unit', 'ref': blocks[1]['ref'],
             'block_ids': ['settings-results', 'requirements-results']},
        ]
    return original_batch(service, key, changes)


if __name__ == '__main__':
    workflow.batch = corrected_batch
    workflow.main()
