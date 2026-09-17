"""安装常用工作区 Skill 的轻量入口，详细方法始终维护在 workflows。

默认只预览；--apply 新建入口。拒绝覆盖内容不同的已有技能，不修改全局技能、
权限或客户端设置。仓库保留目录若只读，应按环境审批流程执行此具体安装。
"""
import argparse
import difflib
import hashlib
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
# 默认发现入口与 --name 的允许集合使用同一登记；完整方法仍只维护在
# workflows，升级此脚本不会覆盖用户已修改的本地 Skill。
NAMES = ("work-loop", "context-maintenance", "evidence-inspection", "development-checks",
         "material-query", "association-exploration", "semantic-maintenance", "consolidate-results")
COMPAT_NAMES = ()
RETIRED_NAMES = ("research-loop", "workspace-context")


# 2026-09-13 前受控发现入口的 LF/CRLF 字节指纹；只迁移完全匹配者。
# 不根据名称或一段模板文字认定用户文件可替换，旧方法保留在Git历史，当前入口已退休。
PREVIOUS_MANAGED = {'association-exploration': ['2979f6fa4114059618bc364c60e307e410b4efbb6dcdbb560386aa991a58107f', '4d2ed7c2bac82422983715b9ef99ce3ecb3e40f4715cd1a954797a27c8f484a8'], 'context-maintenance': ['84543bac5b571ce3ba7414ec1675d19e5b0c0827feb280c986dc6ce5f86a3fbd', '8538d7d6cf5db31d1ea99ea6595b81050db803aba706df589ecb1b34038de017'], 'development-checks': ['3ac90d2b123399b8596baa69542ca5765a43e19fea7829aa33cef9b910dff4fe', '9243cb98b16feefbf387dbeae7a4117aace8b08ccf30d06277e739e9b0495675'], 'evidence-inspection': ['387eebe30817e291f83f5795d0ec4a51891822f6fa2cb60ba8f8efd11eaca9dc', 'd776775be39c097b2be50a4b338e712135c7b8c9162f3f615caf6f6d7afa9ec8'], 'material-query': ['4756d3e9e6043e1a060b2b9e9ad7d3ad9163ca12731f2484e8e1792d6fcb82f1', '8caa9093fab6cc480805f7610e94c190b89c0a1c06d867044584a70a7b2dbc1f'], 'research-loop': ['2c9ce71079e07e313386bb56f0e7bc87fc633e80d3cf70efc5d43e0f4195fd93', 'e677af033a799a61184590c4bc03d3586f5e0cfd16b4c330afbaa0f4f5a05237'], 'semantic-maintenance': ['5c1c16cc595f533bd9822e1646be8f3ebce782ee05fdbc7ae6be3d897ef9ecb3', 'd5e5268a7a1786243b69679e1c9056d8026cc4d6490e88038873d16b10cd959a'], 'workspace-context': ['4184ada37071ed999403c2e490df26acfea1f6fb0e2f0755fcf3d978a09576e2', 'a3566b779aed9ffc1371b1df35301f7507c19e47a5c9fcedbea9a6a4a884cbbc']}


def generated(root, name):
    text = (Path(root) / 'automation/workflows' / name / 'SKILL.md').read_text(encoding='utf-8')
    frontmatter = re.match(r"---\s*\n(.*?)\n---", text, re.S)
    if not frontmatter:
        raise ValueError('工作流缺少 frontmatter：' + name)
    return "---\n" + frontmatter.group(1) + "\n---\n\n# 工作区技能入口\n\n" + (
        f"在含 workspace.json 的当前研发工作区使用。读取 [完整工作流](../../../automation/workflows/{name}/SKILL.md)，"
        "按本轮任务执行；根 AGENTS 与用户明确要求优先。本文件只用于技能发现，方法和命令在工作流源维护。\n")


def managed_updates(source, target):
    """供 setup 的预览/备份/恢复事务使用；不直接写文件或删除目录。"""
    from deployment import safe, digest
    entries = []
    for name, fingerprints in PREVIOUS_MANAGED.items():
        relative = '.agents/skills/' + name + '/SKILL.md'
        file = safe(target, relative)
        before = digest(file)
        if before not in fingerprints:
            continue
        if name in RETIRED_NAMES:
            entries.append({'path': relative, 'before': before, 'after': None})
        else:
            content = generated(source, name)
            if file.read_text(encoding='utf-8') != content:
                entries.append({'path': relative, 'before': before,
                                'after': hashlib.sha256(content.encode()).hexdigest(), 'content': content})
    return entries


def install(apply=False, names=None):
    entries = []
    selected = NAMES if names is None else tuple(dict.fromkeys(names))
    if not selected or not set(selected).issubset(NAMES + COMPAT_NAMES):
        raise ValueError("只能安装已登记的工作区技能")
    for name in selected:
        target = ROOT / ".agents/skills" / name / "SKILL.md"
        content = generated(ROOT, name)
        if target.exists():
            current = target.read_text(encoding="utf-8")
            if current != content:
                # 冲突仍在批次预检阶段阻止任何写入。只输出供用户合并的
                # 文本差异，不静默替换自定义规则，也不自动应用这些建议。
                difference = "".join(difflib.unified_diff(
                    current.splitlines(keepends=True), content.splitlines(keepends=True),
                    fromfile=str(target) + " (current, preserved)",
                    tofile=str(target) + " (generated proposal)", n=3))
                raise FileExistsError(
                    f"已有不同技能，拒绝覆盖：{target}\n请保留用户规则并按以下差异合并后重试：\n{difference}")
        entries.append((target, content))
    # 所有冲突先检查完，再进行批量写入。删除这些新入口即可撤销本次安装。
    for target, content in entries:
        print(("安装：" if apply else "预览：") + str(target))
        if apply and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--name", choices=NAMES + COMPAT_NAMES, action="append", help="只安装指定入口，保留其他本地修改；可重复")
    args = parser.parse_args()
    try:
        install(args.apply, args.name)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
