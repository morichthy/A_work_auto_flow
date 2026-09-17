#!/usr/bin/env python3
"""AI 研发工作区的零依赖控制平面 CLI。

这个脚本刻意只使用 Python 标准库，方便在受限的 Windows 研发环境中启动。
它只管理元数据与小型文本，不读取或复制公司共享盘上的真实大数据。

主要能力：
1. 从仓库模板创建项目、专题研究和分析 Run；
2. 生成可重建的工作区索引；
3. 按显式范围构建有字符预算的 AI 上下文包；
4. 校验目录、JSON、内部链接、疑似秘密和意外大文件。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

# CLI 可从子目录启动，也可由测试通过文件路径加载。检索模块与本入口同目录，
# 显式加入此可信路径，避免依赖调用者 cwd；不加载外部插件或模型。
sys.path.insert(0, str(Path(__file__).resolve().parent))
import retrieval
import evidence as evidence_controls
from manifest_discovery import manifests, run_home


# 只有这些小型文本类型会进入上下文包或内容安全检查。二进制文件始终按路径处理，
# 避免误解码、上下文爆炸和把大型工程数据意外带入 AI 会话。
TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".json",
    ".jsonl",
    ".toml",
    ".yaml",
    ".yml",
    ".py",
    ".ps1",
}

# 这里只检测高置信度秘密形态。不要加入宽泛的 ``password=`` 规则，否则模板、
# 文档和测试很容易误报。真正的秘密扫描应由公司批准的专用工具在 CI 中执行。
HIGH_CONFIDENCE_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[opusr]_[A-Za-z0-9_]{30,}\b")),
)

MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
PLACEHOLDER_RE = re.compile(r"\{\{[a-zA-Z0-9_]+\}\}")


def now_utc() -> datetime:
    """返回带时区 UTC 时间，确保跨机器 Run ID 和 manifest 不含歧义。"""

    return datetime.now(timezone.utc)


def iso_now() -> str:
    """生成秒级 ISO 8601 时间；秒级已足够用于人类可读元数据。"""

    return now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def find_workspace_root(start: Path | None = None) -> Path:
    """从起始目录向上寻找 ``workspace.json``，避免依赖调用者的 cwd。

    找不到时立即失败，而不是猜测目录。错误的根目录会让创建命令在错误位置写文件，
    因而这是所有写操作之前的安全边界。
    """

    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "workspace.json").is_file():
            return candidate
    raise FileNotFoundError("未找到 workspace.json；请从工作区内运行此命令。")


def load_json(path: Path) -> Any:
    """以 UTF-8 读取 JSON，并让解析错误保留准确文件与行列信息。"""

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(data: Any) -> str:
    """统一 JSON 格式，便于 Git diff 与人工审阅。"""

    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def atomic_write_text(path: Path, content: str, dry_run: bool = False) -> None:
    """通过同目录临时文件原子替换，避免中断留下半个 manifest。

    临时文件放在目标目录，保证 Windows 上 ``os.replace`` 不跨卷。写入失败时旧文件
    保持不变。``dry_run`` 只打印目标，不触碰文件系统。
    """

    if dry_run:
        print(f"[dry-run] 写入 {path}")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temp_path, path)
    finally:
        # ``os.replace`` 成功后临时路径已不存在；失败时尽力清理，不掩盖原始异常。
        if temp_path.exists():
            temp_path.unlink()


def slugify(value: str) -> str:
    """把用户输入标准化为跨平台安全的 kebab-case slug。"""

    normalized = value.strip().lower().replace("_", " ")
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    normalized = re.sub(r"-{2,}", "-", normalized)
    if not normalized:
        raise ValueError("slug 必须至少包含一个 ASCII 字母或数字。")
    if len(normalized) > 64:
        raise ValueError("slug 最长 64 个字符；请使用短而稳定的标识。")
    return normalized


def stable_id(prefix: str, slug: str) -> str:
    """生成可读且稳定的对象 ID；slug 改名应被视为显式迁移。"""

    return f"{prefix}-{slug.upper()}"


def ensure_inside(root: Path, path: Path) -> Path:
    """解析路径并确认其仍在工作区内，防止模板或参数越界写入。"""

    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise ValueError(f"路径越出工作区：{resolved_path}")
    return resolved_path


def render_template_tree(
    source: Path,
    destination: Path,
    replacements: dict[str, str],
    *,
    dry_run: bool = False,
) -> None:
    """复制模板树并替换文本占位符，绝不覆盖已有目标。

    模板目录只应包含小型文本。仍保留二进制分支，使以后加入获批模板资产时不会
    因错误解码而损坏文件；二进制文件仅原样复制。
    """

    if destination.exists():
        raise FileExistsError(f"目标已存在，拒绝覆盖：{destination}")
    if dry_run:
        print(f"[dry-run] 从 {source} 创建 {destination}")
        return

    destination.mkdir(parents=True)
    try:
        for source_path in sorted(source.rglob("*")):
            relative = source_path.relative_to(source)
            target_path = destination / relative
            if source_path.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            if source_path.suffix.lower() in TEXT_SUFFIXES or source_path.name == ".gitkeep":
                text = source_path.read_text(encoding="utf-8")
                # JSON 模板中的占位符位于字符串内，标题含引号、反斜线或换行时
                # 必须先转义；Markdown 则保留原文本。一次替换避免标题本身含
                # {{date}} 等字面量时又被后续替换篡改。
                values = {
                    token: json.dumps(value, ensure_ascii=False)[1:-1]
                    if source_path.suffix.lower() == ".json" else value
                    for token, value in replacements.items()
                }
                text = PLACEHOLDER_RE.sub(lambda match: values.get(match.group(), match.group()), text)
                target_path.write_text(text, encoding="utf-8", newline="\n")
            else:
                shutil.copy2(source_path, target_path)
    except Exception:
        # 新目标此前不存在，因此失败时删除半成品是可恢复且边界明确的清理。
        shutil.rmtree(destination, ignore_errors=True)
        raise


def create_project(root: Path, slug_value: str, title: str, dry_run: bool = False) -> Path:
    """从项目模板创建一个新的项目控制平面。"""

    slug = slugify(slug_value)
    destination = ensure_inside(root, root / "projects" / slug)
    replacements = {
        "{{project_id}}": stable_id("PRJ", slug),
        "{{project_slug}}": slug,
        "{{title}}": title.strip() or slug,
        "{{date}}": now_utc().date().isoformat(),
    }
    render_template_tree(root / "projects" / "_template", destination, replacements, dry_run=dry_run)
    print(f"已创建项目：{destination}")
    return destination


def create_research(root: Path, slug_value: str, title: str, dry_run: bool = False) -> Path:
    """从研究模板创建一个新的专题研究闭环。"""

    slug = slugify(slug_value)
    destination = ensure_inside(root, root / "research" / slug)
    replacements = {
        "{{research_id}}": stable_id("RES", slug),
        "{{research_slug}}": slug,
        "{{title}}": title.strip() or slug,
        "{{date}}": now_utc().date().isoformat(),
    }
    render_template_tree(root / "research" / "_template", destination, replacements, dry_run=dry_run)
    print(f"已创建研究：{destination}")
    return destination


def detect_git_revision(root: Path) -> dict[str, Any]:
    """尽力读取 Git revision；非 Git 工作区使用显式 null，不伪造版本。"""

    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
        )
        return {"commit": commit, "dirty": dirty}
    except (FileNotFoundError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}


def create_module(root: Path, slug_value: str, title: str, dry_run: bool = False,
                  source_document: str | None = None) -> Path:
    """创建公司文档定义的核心算法；保留函数名和 MOD-ID 以兼容引用。

    文档引用是准入所需的来源记录，不在此读取外部文件，也不伪判文档
    已读、公司认可或模型有效。真实业务资格由接入时核对材料确定。
    """
    if not isinstance(source_document, str) or not source_document.strip():
        raise ValueError("核心算法必须提供公司算法/模块文档引用（--source-document）；普通脚本请归入 tools/automation/runs，待分类材料放 inbox/research。")
    slug = slugify(slug_value)
    target = ensure_inside(root, root / "core-algorithms" / slug)
    render_template_tree(root / "core-algorithms/_template", target, {
        "{{module_id}}": stable_id("MOD", slug), "{{module_slug}}": slug,
        "{{title}}": title.strip() or slug, "{{date}}": now_utc().date().isoformat(),
        "{{source_document}}": source_document.strip(),
    }, dry_run=dry_run)
    print(f"{'[dry-run] 将创建' if dry_run else '已创建'}核心算法：{target}")
    return target


def create_run(root: Path, project_slug: str | None, title: str, dry_run: bool = False,
               keywords: Sequence[str] = (), module_ids: Sequence[str] = (),
               research_ids: Sequence[str] = (), owner_id: str | None = None) -> Path:
    """创建一次不可混淆的分析/仿真 Run 目录和初始 manifest。"""

    project_metadata = {}
    if project_slug:
        # 兼容旧位置参数，同时记录项目关联；显式 owner 决定唯一物理归属。
        project_metadata_path = ensure_inside(root, root / "projects" / slugify(project_slug) / "project.json")
        if not project_metadata_path.is_file():
            raise FileNotFoundError(f"关联项目不存在：{project_slug}")
        project_metadata = load_json(project_metadata_path)
    moment = now_utc()
    # 显示标题可为任意语言；ID 不再依赖标题翻译，随机后缀避免批量运行同秒碰撞。
    if not title.strip():
        raise ValueError("Run 标题不能为空")
    run_id = f"RUN-{moment.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:12].upper()}"
    selected_owner = owner_id
    if not selected_owner:
        related_research = list(dict.fromkeys(research_ids))
        if len(related_research) > 1:
            raise ValueError('多个研究关联存在归属歧义，请用 --owner 指定唯一对象')
        # 研究优先于大型交付项目；多个模块仅是关联，不随意选择第一个。
        selected_owner = (related_research[0] if related_research else
                          project_metadata.get('project_id') or
                          (module_ids[0] if len(set(module_ids)) == 1 else None))
    parent, selected_owner = run_home(root, selected_owner) if selected_owner else (root / 'runs', None)
    inherited_sensitivity = None
    if selected_owner:
        # 物理归属不能把受限专题的标题/运行降为默认 internal。创建时继承
        # 已登记对象分类；无归属旧行为保持兼容，不凭关联猜测其他对象权限。
        from memory.owners import resolve_owner
        inherited_sensitivity = resolve_owner(root, selected_owner)['native_data'].get('sensitivity', 'internal')
    run_dir = ensure_inside(root, parent / run_id.lower())
    if run_dir.exists():
        raise FileExistsError(f"Run 已存在，请稍后重试或更换标题：{run_dir}")

    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "owner_id": selected_owner,
        "project_id": project_metadata.get("project_id"),
        "title": title,
        "keywords": list(dict.fromkeys(word.strip() for word in keywords if word.strip())),
        "review_history": [],
        # 空结论集合只表示探索尚未形成正式依据；accepted 必须逐条复核。
        "claims": [],
        "dependencies": [],
        "run_type": "analysis",
        "status": "planned",
        "created_at": moment.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "started_at": None,
        "ended_at": None,
        "owner": None,
        "question": "",
        "hypotheses": [],
        "inputs": [],
        "parameters": {},
        "code": detect_git_revision(root),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "lock_or_image_digest": None,
        },
        "random_seeds": [],
        "quality_results": [],
        "metrics": {},
        "artifacts": [],
        "lineage_events": "lineage.jsonl",
        "conclusion": "",
        "limitations": [],
        "parent_run_ids": [],
        "related_module_ids": list(dict.fromkeys(module_ids)),
        "related_research_ids": list(dict.fromkeys(research_ids)),
        "related_dataset_ids": [],
        "review": {"status": "not-reviewed", "reviewer": None, "date": None},
    }
    if inherited_sensitivity is not None:
        manifest['sensitivity'] = inherited_sensitivity

    readme = f"# {run_id}：{title}\n\n"
    readme += "## 问题与成功标准\n\n- 问题：\n- 假设：\n- 成功/证伪标准：\n\n"
    readme += "## 输入与范围\n\n- 数据资产/版本/指纹：\n- 时间窗与字段：\n- 排除条件：\n\n"
    readme += "## 方法与参数\n\n说明变换、算法、单位、环境、随机种子和容差来源。\n\n"
    readme += "## 结果与验证\n\n区分事实、计算结果、推断和建议；引用产物相对路径。\n\n"
    readme += "## 结论、限制与下一步\n\n- 结论：\n- 限制：\n- 下一步：\n"

    if dry_run:
        print(f"[dry-run] 创建 Run：{run_dir}")
        return run_dir

    run_dir.mkdir(parents=True)
    atomic_write_text(run_dir / "run.json", dump_json(manifest))
    atomic_write_text(run_dir / "README.md", readme)
    atomic_write_text(run_dir / "lineage.jsonl", "")
    print(f"已创建 Run：{run_dir}")
    return run_dir


REVIEW_STATES = {"not-reviewed", "accepted", "disputed", "retracted", "superseded"}
UNSAFE_REVIEW_STATES = {"disputed", "retracted", "superseded"}


def collect_runs(root: Path) -> list[dict[str, Any]]:
    """只读约定目录里的 manifest，不扫日志或共享盘；坏记录显式报错。

    缺失新增字段的旧记录仍能检索；未知复核状态不会被当作已确认。
    ID 冲突必须停止，避免复核错误对象。
    """
    records = []
    seen: set[str] = set()
    paths = manifests(root, {'run.json'})
    for path in sorted(paths):
        if "_template" in path.parts:
            continue
        ensure_inside(root, path)
        data = load_json(path)
        run_id = data.get("run_id") if isinstance(data, dict) else None
        if not isinstance(run_id, str) or not run_id or run_id.casefold() in seen:
            raise ValueError(f"缺失或重复 Run ID：{path}")
        if data.get('owner_id') is not None and (not isinstance(data['owner_id'], str) or not data['owner_id'].strip()):
            raise ValueError(f"{path}: owner_id 必须为非空对象 ID 或 null")
        for key in ("keywords", "parent_run_ids", "review_history"):
            if not isinstance(data.get(key, []), list):
                raise ValueError(f"{path}: {key} 必须是数组")
        if not all(isinstance(v, str) for v in data.get("parent_run_ids", [])):
            raise ValueError(f"{path}: parent_run_ids 必须是字符串数组")
        if not isinstance(data.get("review", {}), dict):
            raise ValueError(f"{path}: review 必须是对象")
        if not isinstance(data.get("review", {}).get("status", "not-reviewed"), str):
            raise ValueError(f"{path}: review.status 必须是字符串")
        if not isinstance(data.get("created_at", ""), str):
            raise ValueError(f"{path}: created_at 必须是字符串")
        seen.add(run_id.casefold())
        records.append({**data, "path": path.relative_to(root).as_posix()})
    return records


def annotate_run_impacts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """沿 parent_run_ids 动态传播待复核信号，不篡改下游历史结论。

    固定点迭代可处理跨项目依赖与环；缺失父记录也必须提示证据缺口。
    accepted 仅代表复核状态，不能消除上游撤回造成的影响。
    """
    by_id = {record["run_id"]: record for record in records}
    blockers: dict[str, set[str]] = {}
    for run_id, record in by_id.items():
        status = record.get("review", {}).get("status", "not-reviewed")
        blockers[run_id] = {run_id} if status in UNSAFE_REVIEW_STATES or status not in REVIEW_STATES else set()
        blockers[run_id].update(p for p in record.get("parent_run_ids", []) if p not in by_id)
    changed = True
    while changed:
        changed = False
        for run_id, record in by_id.items():
            old = len(blockers[run_id])
            for parent in record.get("parent_run_ids", []):
                blockers[run_id].update(blockers.get(parent, set()))
            changed |= len(blockers[run_id]) != old
    return [{**record, "needs_revalidation": bool(blockers[record["run_id"]]),
             "blocking_run_ids": sorted(blockers[record["run_id"]])} for record in records]


def search_runs(root: Path, query: str = "", project: str | None = None,
                limit: int = 20) -> list[dict[str, Any]]:
    """即时检索源元数据，避免撤回后仍命中旧缓存。空格分隔词按 AND 匹配。

    中文使用子串匹配，关键词由 AI/用户显式填写；不把不可靠的自动分词
    或语义相似度误称为事实判定。排序只用于导航，所有状态均可返回。
    """
    if limit < 1:
        raise ValueError("limit 必须大于零")
    records = annotate_run_impacts(collect_runs(root))
    terms = query.casefold().split()
    matches = []
    for record in records:
        if project and record.get("project_id") != stable_id("PRJ", slugify(project)):
            continue
        searchable = {k: record.get(k) for k in (
            "run_id", "title", "question", "conclusion", "keywords", "related_dataset_ids",
            "related_module_ids", "parameters", "limitations")}
        haystack = json.dumps(searchable, ensure_ascii=False).casefold()
        if all(term in haystack for term in terms):
            matches.append(record)
    return sorted(matches, key=lambda r: (r.get("created_at", ""), r["run_id"]), reverse=True)[:limit]


def review_run(root: Path, run_id: str, status: str, reviewer: str, reason: str,
               evidence: str = "", scope: str = "", replacement: str = "",
               dry_run: bool = False) -> dict[str, Any]:
    """追加复核事件并原子替换同一 manifest，保留先前复核与原始结论。

    本命令登记人或已授权验证流程的判断，不认证 reviewer 身份或证据真伪。
    一个 manifest 单写者使用；多任务并发复核同一对象前需串行协调。
    """
    records = collect_runs(root)
    by_id = {r["run_id"]: r for r in records}
    if run_id not in by_id:
        raise ValueError(f"找不到 Run：{run_id}")
    if status not in REVIEW_STATES or not reviewer.strip() or not reason.strip():
        raise ValueError("需要有效复核状态、reviewer 和 reason")
    if status == "accepted" and (not evidence.strip() or not scope.strip()):
        raise ValueError("accepted 必须明确 evidence 与 scope；执行成功不等于结论正确")
    if status == "superseded" and (replacement not in by_id or replacement == run_id):
        raise ValueError("superseded 必须引用另一个已存在 Run")
    if replacement and status != "superseded":
        raise ValueError("replacement 仅用于 superseded")
    record = dict(by_id[run_id])
    path = ensure_inside(root, root / record.pop("path"))
    previous = dict(record.get("review", {"status": "not-reviewed"}))
    current = {"status": status, "reviewer": reviewer, "date": iso_now(),
               "reason": reason, "evidence": evidence, "scope": scope,
               "replacement_run_id": replacement or None}
    record.setdefault("review_history", []).append({"previous": previous, "current": current})
    record["review"] = current
    atomic_write_text(path, dump_json(record), dry_run=dry_run)
    # 只计算影响，不自动宣布下游结论错误；需要按实际引用与适用域复核。
    updated = [{**record, "path": path.relative_to(root).as_posix()} if r["run_id"] == run_id else r
               for r in records]
    affected = [r["run_id"] for r in annotate_run_impacts(updated)
                if run_id in r["blocking_run_ids"] and r["run_id"] != run_id]
    graph = evidence_controls.EvidenceGraph(root, {path: record})
    return {"run_id": run_id, "review": current, "affected_run_ids": affected,
            "affected_evidence_ids": graph.status(run_id)["affected_ids"], "dry_run": dry_run}


def safe_metadata_records(paths: Iterable[Path], id_field: str) -> tuple[list[dict[str, Any]], list[str]]:
    """读取索引元数据；坏文件作为警告返回，不让整个索引悄悄缺失。"""

    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    for path in sorted(paths):
        try:
            data = load_json(path)
            if not isinstance(data, dict):
                raise ValueError("对象元数据必须是 JSON 对象")
            records.append(
                {
                    "id": data.get(id_field, "UNKNOWN"),
                    "title": data.get("title") or data.get("name") or path.parent.name,
                    "status": data.get("status", "unknown"),
                    "path": path,
                }
            )
        except (OSError, ValueError) as exc:
            warnings.append(f"无法索引 {path}: {exc}")
    return records, warnings


def markdown_table(records: Sequence[dict[str, Any]], root: Path) -> str:
    """把对象记录渲染成稳定 Markdown 表；空集合显式显示而不是消失。"""

    if not records:
        return "_暂无已登记对象。_\n"
    lines = ["| ID | 标题 | 状态 | 入口 |", "|---|---|---|---|"]
    for record in records:
        relative = Path(record["path"]).relative_to(root).as_posix()
        title = str(record["title"]).replace("|", "\\|")
        # 索引固定写入 ``context/generated/``，因此链接需要回到工作区根再进入对象路径。
        # 显式相对链接比绝对本机路径更适合 Git、其他电脑和不同 AI 客户端。
        lines.append(
            f"| `{record['id']}` | {title} | `{record['status']}` | "
            f"[{relative}](../../{relative}) |"
        )
    return "\n".join(lines) + "\n"


def refresh_index(root: Path, dry_run: bool = False) -> tuple[Path, list[str]]:
    """从对象元数据派生轻量索引；不读取共享盘和运行产物内容。"""

    modules, module_warnings = safe_metadata_records(
        (p for p in (root / "core-algorithms").glob("*/module.json") if "_template" not in p.parts), "module_id")
    projects, project_warnings = safe_metadata_records(
        (path for path in (root / "projects").glob("*/project.json") if "_template" not in path.parts),
        "project_id",
    )
    research, research_warnings = safe_metadata_records(
        (path for path in (root / "research").glob("*/research.json") if "_template" not in path.parts),
        "research_id",
    )
    datasets, dataset_warnings = safe_metadata_records(
        (
            path
            for path in (root / "data" / "catalog").glob("*.dataset.json")
            if "example" not in path.name.lower()
        ),
        "dataset_id",
    )
    warnings = [*module_warnings, *project_warnings, *research_warnings, *dataset_warnings]

    try:
        tool_data = load_json(root / "tools" / "registry.json")
        tools = [
            {
                "id": item.get("tool_id", "UNKNOWN"),
                "title": item.get("name", "unnamed"),
                "status": item.get("status", "unknown"),
                "path": root / item.get("entrypoint", "tools/registry.json"),
            }
            for item in tool_data.get("tools", [])
        ]
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        tools = []
        warnings.append(f"无法索引 tools/registry.json: {exc}")

    def knowledge_records(directory: str, prefix: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in sorted((root / "knowledge" / directory).glob("*.md")):
            if "TEMPLATE" in path.name:
                continue
            records.append({"id": f"{prefix}-{path.stem}", "title": path.stem, "status": "document", "path": path})
        return records

    content = [
        "# 工作区派生索引",
        "",
        f"生成时间：{iso_now()}",
        "",
        "> 本文件由 `workspace_cli.py refresh-index` 生成，只用于导航；对象附近的元数据和正式文档才是事实源。",
        "",
        "## 核心算法",
        "",
        markdown_table(modules, root).rstrip(),
        "",
        "## 项目（可选聚合）",
        "",
        markdown_table(projects, root).rstrip(),
        "",
        "## 专题研究",
        "",
        markdown_table(research, root).rstrip(),
        "",
        "## 数据资产",
        "",
        markdown_table(datasets, root).rstrip(),
        "",
        "## 工具",
        "",
        markdown_table(tools, root).rstrip(),
        "",
        "## 决策",
        "",
        markdown_table(knowledge_records("decisions", "ADR"), root).rstrip(),
        "",
        "## 复盘",
        "",
        markdown_table(knowledge_records("incidents", "INC"), root).rstrip(),
        "",
        "## 模式",
        "",
        markdown_table(knowledge_records("patterns", "PATTERN"), root).rstrip(),
        "",
    ]
    output = root / "context" / "generated" / "workspace-index.md"
    runs = annotate_run_impacts(collect_runs(root))
    # 主入口仅展示近期 20 项，完整 JSON 索引留在磁盘，不常驻全部历史。
    run_rows = [{"id": r["run_id"], "title": r.get("title", ""),
                 "status": f"{r.get('status', 'unknown')} / {r.get('review', {}).get('status', 'not-reviewed')}"
                           + (" / needs-revalidation" if r["needs_revalidation"] else ""),
                 "path": root / r["path"]} for r in sorted(
                     runs, key=lambda r: (r.get("created_at", ""), r["run_id"]), reverse=True)[:20]]
    content.extend(["## Run（最近 20 项）", "", f"共 {len(runs)} 项；使用 search-runs 按关键词检索源记录。",
                    "", markdown_table(run_rows, root)])
    # 仅保存检索字段与状态，日志和大产物始终通过原记录按需读取。
    fields = ("run_id", "project_id", "title", "created_at", "status", "review", "keywords",
              "question", "conclusion", "parent_run_ids", "path", "needs_revalidation", "blocking_run_ids")
    atomic_write_text(root / "context/generated/run-index.json",
                      dump_json([{k: r.get(k) for k in fields} for r in runs]), dry_run=dry_run)
    atomic_write_text(output, "\n".join(content), dry_run=dry_run)
    print(f"已刷新索引：{output}")
    return output, warnings


def is_excluded(relative: Path, excluded_directories: Sequence[str]) -> bool:
    """按路径组件判断排除，避免简单字符串前缀把相似目录误排除。"""

    # RS 的可读副本不能被通用上下文扫描全量注入；AI 通过经过授权与预算
    # 检查的 reading-handoff 选择当前笔记，避免把所有历史阅读重复装入。
    normalized_exclusions = {Path(item).as_posix().strip("/") for item in excluded_directories} | {".local", "context/reading-notes"}
    relative_posix = relative.as_posix()
    return any(
        relative_posix == excluded or relative_posix.startswith(excluded + "/")
        for excluded in normalized_exclusions
    )


def build_context(
    root: Path,
    *,
    project: str | None = None,
    module: str | None = None,
    research: str | None = None,
    task: str = "",
    output: Path | None = None,
    dry_run: bool = False,
) -> Path:
    """生成受字符预算约束的 L0-L2 上下文包。

    这是显式清单式收集，而非递归全文检索。它不会读取 Run 产物、archive、inbox、
    共享盘或二进制文件。项目/研究内部只加载入口元数据与地图；更深证据由执行任务的
    AI 根据这些链接按需读取。
    """

    config = load_json(root / "workspace.json")
    policy = config["context_policy"]
    max_total = int(policy.get("max_context_chars", 120_000))
    max_file = int(policy.get("max_single_file_chars", 30_000))
    excluded = policy.get("excluded_directories", [])

    index_path, warnings = refresh_index(root, dry_run=dry_run)
    if warnings:
        for warning in warnings:
            print(f"[warning] {warning}", file=sys.stderr)

    candidates: list[Path] = []
    for relative in [*policy.get("always_include", []), *policy.get("navigation_include", [])]:
        candidates.append(root / relative)

    if module:
        module_slug = slugify(module)
        module_dir = root / "core-algorithms" / module_slug
        if not (module_dir / "module.json").is_file():
            raise FileNotFoundError(f"找不到核心算法：{module_slug}")
        candidates.append(root / "core-algorithms/AGENTS.md")
        candidates.extend(module_dir / relative for relative in ("AGENTS.md", "module.json", "README.md"))

    if project:
        project_slug = slugify(project)
        project_dir = root / "projects" / project_slug
        if not (project_dir / "project.json").is_file():
            raise FileNotFoundError(f"找不到项目：{project_slug}")
        candidates.extend(
            project_dir / relative
            for relative in ("AGENTS.md", "project.json", "README.md", "context/MODULE_MAP.md")
        )

    if research:
        research_slug = slugify(research)
        research_dir = root / "research" / research_slug
        if not (research_dir / "research.json").is_file():
            raise FileNotFoundError(f"找不到研究：{research_slug}")
        candidates.extend(
            research_dir / relative
            for relative in ("research.json", "README.md", "PLAN.md", "SYNTHESIS.md")
        )

    # 保序去重，保证输出稳定，避免同一文件同时出现在 always/navigation 中。
    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = ensure_inside(root, candidate)
        if resolved not in seen:
            seen.add(resolved)
            unique_candidates.append(resolved)

    header = [
        "# 任务上下文包",
        "",
        f"生成时间：{iso_now()}",
        f"任务：{task or '未提供；执行前必须明确'}",
        f"项目：{project or '未指定'}",
        f"核心算法：{module or '未指定'}",
        f"研究：{research or '未指定'}",
        "",
        "> 这是有界派生视图，不是事实源。遇到冲突时回到标注的源文件。",
        "",
    ]
    chunks = ["\n".join(header)]
    used = len(chunks[0])

    for candidate in unique_candidates:
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(root)
        if is_excluded(relative, excluded) or candidate.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = candidate.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_file:
            text = text[:max_file] + "\n\n[该源文件已按单文件预算截断]\n"
        section = f"\n---\n\n## Source: `{relative.as_posix()}`\n\n{text.rstrip()}\n"
        if used + len(section) > max_total:
            chunks.append("\n---\n\n[已达到上下文总预算，其余源文件未加入]\n")
            break
        chunks.append(section)
        used += len(section)

    target = output or (root / "context" / "generated" / "context-pack.md")
    target = ensure_inside(root, target if target.is_absolute() else root / target)
    atomic_write_text(target, "".join(chunks), dry_run=dry_run)
    print(f"已生成上下文包：{target}（约 {used} 字符）")
    return target


def control_files(root: Path) -> Iterable[Path]:
    """Prune local/third-party caches before walking: neither business schema
    checks nor large-file warnings should inspect generated test workspaces."""
    # Reserved raw execution containers are data, not workspace control files.
    # Their enclosing Run and genuine business cards remain fully validated.
    ignored = {'.run-captures', '.git', '.local', '.venv', '__pycache__', 'tmp', 'dist',
               'node_modules', 'test-results', 'playwright-report'}
    runtime = {'services/qdrant/runtime', 'services/qdrant/models',
               'services/qdrant/wheelhouse', 'services/qdrant/downloads'}
    for folder, dirs, files in os.walk(root, followlinks=False):
        base = Path(folder)
        dirs[:] = [d for d in dirs if d not in ignored and (base / d).relative_to(root).as_posix() not in runtime
                   and not (base / d).is_symlink() and not (base / d).is_junction()]
        for name in files:
            path = base / name
            if not path.is_symlink():
                yield path


def iter_small_text_files(root: Path, max_bytes: int = 1_000_000) -> Iterable[Path]:
    """迭代小型文本，跳过缓存、Git 与明显生成/归档目录。"""

    excluded = {".git", ".local", ".venv", "__pycache__", "archive", "tmp", "dist", "reports/generated", "retrieval/generated",
                "services/qdrant/runtime", "services/qdrant/models", "services/qdrant/wheelhouse", "services/qdrant/downloads"}
    for path in control_files(root):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if any(part in excluded for part in relative.parts) or is_excluded(relative, list(excluded)):
            continue
        try:
            if path.stat().st_size <= max_bytes:
                yield path
        except OSError:
            continue


def validate_workspace(root: Path) -> tuple[list[str], list[str]]:
    """返回 ``(errors, warnings)``，由 CLI 决定退出码。"""

    errors: list[str] = []
    warnings: list[str] = []

    try:
        config = load_json(root / "workspace.json")
    except (OSError, json.JSONDecodeError) as exc:
        return [f"workspace.json 无法读取：{exc}"], warnings

    for relative in config.get("required_paths", []):
        if not (root / relative).exists():
            errors.append(f"缺少必需路径：{relative}")

    # 结构校验只能发现漏填和错类别；非空来源不能替代业务文档核对。
    for card in (root / "core-algorithms").glob("*/module.json"):
        if card.parent.name == "_template":
            continue
        try:
            item = load_json(card)
            if not isinstance(item, dict) or item.get("entity_kind") != "core-algorithm":
                errors.append(f"核心算法类别缺失或错误：{card.relative_to(root)}")
                continue
            source = item.get("source_document")
            if not isinstance(source, str) or not source.strip():
                errors.append(f"核心算法缺少公司文档引用：{card.relative_to(root)}")
        except (OSError, ValueError):
            pass  # 通用 JSON 校验在下方统一报告读取错误。

    for path in control_files(root):
        if path.suffix.lower() != '.json':
            continue
        # 根目录的迁移包与解压测试副本不是控制平面，不能重复审计其中的第三方文件。
        if path.relative_to(root).parts[0] in {"tmp", "dist"}:
            continue
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        if path.relative_to(root).as_posix().startswith("services/qdrant/"):
            continue  # 第三方运行时由安装清单与 health 检查，不当工作区 schema/链接审计。
        try:
            load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"JSON 无效：{path.relative_to(root)}：{exc}")

    # 非模板文件残留占位符通常意味着创建/迁移未完成；模板自身允许保留占位符。
    for path in iter_small_text_files(root):
        relative = path.relative_to(root)
        text = path.read_text(encoding="utf-8", errors="replace")
        # context-pack 会把多个源文件原样嵌入同一位置，源文件中的相对链接在这个临时
        # 视图内自然不再以相同基准解析。校验正式源和 workspace-index 即可，跳过包内链接。
        is_generated_context_pack = relative.as_posix() == "context/generated/context-pack.md"
        # Python/PowerShell 源码可能需要处理 ``{{token}}`` 字面量，所以只在文档和
        # 机器配置中检查未替换占位符，避免把模板引擎实现本身误报为残留模板。
        if (
            path.suffix.lower() in {".md", ".json", ".toml", ".yaml", ".yml"}
            and "_template" not in relative.parts
            and PLACEHOLDER_RE.search(text)
        ):
            warnings.append(f"非模板文件存在未替换占位符：{relative}")

        for label, pattern in HIGH_CONFIDENCE_SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"疑似 {label}：{relative}")

        if path.suffix.lower() == ".md" and not is_generated_context_pack:
            for link_target in MARKDOWN_LINK_RE.findall(text):
                target = link_target.strip().split("#", 1)[0].strip()
                if not target or "://" in target or target.startswith(("mailto:", "#")):
                    continue
                # 带空格的 Markdown 目标可能使用尖括号；这里先去掉包裹符再按源文件解析。
                target = target.strip("<>")
                linked = (path.parent / target).resolve()
                try:
                    ensure_inside(root, linked)
                except ValueError:
                    warnings.append(f"内部链接越出工作区：{relative} -> {target}")
                    continue
                if not linked.exists() and "<" not in target and "{{" not in target:
                    warnings.append(f"内部链接不存在：{relative} -> {target}")

    # 大文件可能表示原始数据或生成产物误入控制平面。只警告，因为公司批准的模板也可能较大。
    for path in control_files(root):
        if path.relative_to(root).parts[0] in {"tmp", "dist"}:
            continue
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.relative_to(root).as_posix().startswith("services/qdrant/"):
            continue
        try:
            if path.stat().st_size > 25 * 1024 * 1024:
                warnings.append(f"控制平面发现大于 25 MiB 的文件：{path.relative_to(root)}")
        except OSError as exc:
            warnings.append(f"无法读取文件大小：{path.relative_to(root)}：{exc}")

    try:
        registry = load_json(root / "tools" / "registry.json")
        for item in registry.get("tools", []):
            entrypoint = item.get("entrypoint")
            if entrypoint:
                # 稳定工具既可以登记单文件 CLI，也可以登记包/脚本集合目录。
                # 此处只验证登记路径存在，不执行工具，也不把目录存在当作
                # Python 包可导入或业务功能已验证；执行能力由工具的 verify 检查。
                entry_path = root / entrypoint
                if not (entry_path.is_file() or entry_path.is_dir()):
                    errors.append(f"工具入口不存在：{item.get('tool_id')} -> {entrypoint}（工作区：{root}）")
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        errors.append(f"工具注册表无法校验：{exc}")

    # 结构有效与科学结论有效是两件事；这里只检查可追踪性缺口。
    try:
        runs = collect_runs(root)
        known_ids = {r["run_id"] for r in runs}
        for run in runs:
            review = run.get("review", {})
            status = review.get("status", "not-reviewed")
            if status not in REVIEW_STATES:
                warnings.append(f"未知复核状态：{run['run_id']} -> {status}")
            if status == "accepted" and not all(review.get(k) for k in ("reviewer", "evidence", "scope")):
                warnings.append(f"已接受 Run 缺少复核者/证据/范围：{run['run_id']}")
            if status == "superseded" and review.get("replacement_run_id") not in known_ids:
                errors.append(f"替代 Run 不存在：{run['run_id']}")
            for parent in run.get("parent_run_ids", []):
                if parent not in known_ids:
                    warnings.append(f"上游 Run 缺失：{run['run_id']} -> {parent}")
    except (OSError, ValueError) as exc:
        errors.append(f"Run 元数据无法校验：{exc}")

    # 新证据关系必须可解析。旧记录继续可读，但执行成功且证据为空时
    # 给出准确警告；正式使用由 check-run / finalize-run 的非零退出码拦截。
    try:
        graph = evidence_controls.EvidenceGraph(root)
        errors.extend("证据元数据：" + problem for problem in graph.errors)
        for nid, node in graph.nodes.items():
            errors.extend(f"证据 {nid}：{problem}" for problem in node["issues"])
            raw = node["raw"]
            if raw.get("run_id") and raw.get("status") == "succeeded":
                missing = [key for key in ("inputs", "artifacts", "quality_results") if not raw.get(key)]
                if missing:
                    warnings.append(f"Run 执行成功但记录不完整：{nid} 缺 {', '.join(missing)}；不得用于正式交付")
            seal = raw.get("finalization")
            if seal and (not isinstance(seal, dict) or seal.get("fingerprint") != node["fingerprint"]):
                errors.append(f"封存后内容变化：{nid}；重新检查并 finalize")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"证据检查无法完成：{exc}")

    return sorted(set(errors)), sorted(set(warnings))


def sha256_file(path: Path) -> str:
    """流式计算文件 SHA-256，供以后报告/产物 manifest 使用。"""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    """集中定义 CLI 契约，使帮助文本与实现保持一致。"""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    retrieval.add_commands(subparsers)
    import run_capture
    run_capture.add_commands(subparsers)
    from workbench_app import cli as relations_cli
    relations_cli.add_commands(subparsers)
    from memory import cli as memory_cli
    memory_cli.add_commands(subparsers)
    from material_query import cli as material_cli
    material_cli.add_commands(subparsers)
    import workspace_settings_cli
    workspace_settings_cli.add_commands(subparsers)
    testing = subparsers.add_parser("testing", help="可复用分级测试：目录、任务选择、执行与验收")
    testing.add_argument("testing_args", nargs=argparse.REMAINDER)

    bench = subparsers.add_parser("workbench", help="一键打开研发工作台；证据、监测、模块与环境状态")
    bench.add_argument("--port", type=int, default=0)
    bench.add_argument("--no-browser", action="store_true")
    bench.add_argument("--demo", action="store_true", help="使用 .local 下独立合成工作区，绝不混入正式材料")
    samples = subparsers.add_parser("test-data", help="生成本机跨模块合成测试工作区，不随 Git/离线包发布")
    samples.add_argument("--preview", action="store_true")

    view_parser = subparsers.add_parser("evidence-view", help="生成证据查看快照，或启动本机只读界面")
    view_parser.add_argument("--serve", action="store_true", help="只监听 127.0.0.1；Ctrl+C 停止")
    view_parser.add_argument("--port", type=int, default=0, help="本地端口，默认自动选择；仅 serve 使用")
    monitor_parser = subparsers.add_parser("evidence-monitor", help="单次只读监测；仅更新本机观察记录与候选")
    monitor_parser.add_argument("--dry-run", action="store_true", help="预览差异，不创建基线或修改日志")

    doctor_parser = subparsers.add_parser("doctor", help="报告当前组件能力；缺依赖不自动安装")
    doctor_parser.add_argument("--require", action="append", default=[],
                               choices=["structure", "fts", "vector", "ocr", "portable", "business-eval"])
    doctor_parser.add_argument("--smoke", action="store_true", help="实际离线探测已安装的模型/OCR")
    verify_parser = subparsers.add_parser("verify", help="能力检查与回归；full 不允许 skipped")
    verify_parser.add_argument("--profile", choices=["core", "full"], default="core")
    evidence_parser = subparsers.add_parser("evidence-status", help="查看结论/文档风险、内容指纹和影响范围")
    evidence_parser.add_argument("target", nargs="?")
    evidence_parser.add_argument("--scope")
    evidence_parser.add_argument("--formal", action="store_true", help="不满足正式使用时返回非零")
    claim_parser = subparsers.add_parser("review-claim", help="逐结论复核与撤回；保留历史，支持预览")
    claim_parser.add_argument("claim_id")
    claim_parser.add_argument("--status", choices=sorted(REVIEW_STATES), required=True)
    for field in ("reviewer", "reason"):
        claim_parser.add_argument("--" + field, required=True)
    for field in ("evidence", "scope", "replacement"):
        claim_parser.add_argument("--" + field, default="")
    claim_parser.add_argument("--dry-run", action="store_true")
    for command in ("check-run", "finalize-run"):
        gate_parser = subparsers.add_parser(command, help="检查正式 Run 记录；finalize 保存内容指纹，不代替科学复核")
        gate_parser.add_argument("run_id")
        gate_parser.add_argument("--scope", required=True)
        if command == "finalize-run":
            gate_parser.add_argument("--dry-run", action="store_true")

    validate_parser = subparsers.add_parser("validate", help="校验工作区结构和高风险问题")
    validate_parser.add_argument("--root", type=Path, help="显式工作区根；默认向上查找")

    project_parser = subparsers.add_parser("new-project", help="从模板创建项目")
    project_parser.add_argument("slug")
    project_parser.add_argument("--title", required=True)
    project_parser.add_argument("--dry-run", action="store_true")

    module_parser = subparsers.add_parser("new-core-algorithm", aliases=["new-module"],
                                        help="创建公司文档定义的核心算法；new-module 为兼容别名")
    module_parser.add_argument("slug")
    module_parser.add_argument("--title", required=True)
    module_parser.add_argument("--source-document", required=True, help="公司算法/模块文档的名称、编号或受控路径；只登记，不自动读取")
    module_parser.add_argument("--dry-run", action="store_true")

    research_parser = subparsers.add_parser("new-research", help="从模板创建专题研究")
    research_parser.add_argument("slug")
    research_parser.add_argument("--title", required=True)
    research_parser.add_argument("--dry-run", action="store_true")

    run_parser = subparsers.add_parser("new-run", help="创建对象内 Run；无归属轻任务保存于根 runs")
    run_parser.add_argument("project", nargs="?", help="可选的旧式项目关联与默认归属")
    run_parser.add_argument("--owner", help="唯一归属对象 ID，优先于研究/项目/模块关联")
    run_parser.add_argument("--module", action="append", default=[], help="关联 MOD-ID，可重复")
    run_parser.add_argument("--research", action="append", default=[], help="关联 RES-ID，可重复")
    run_parser.add_argument("--title", required=True)
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--keyword", action="append", default=[], help="可重复；中文/英文领域关键词")

    search_parser = subparsers.add_parser("search-runs", help="检索 Run 元数据并显示复核/依赖风险")
    search_parser.add_argument("query", nargs="?", default="")
    search_parser.add_argument("--project")
    search_parser.add_argument("--limit", type=int, default=20)

    review_parser = subparsers.add_parser("review-run", help="追加确认/质疑/撤回记录并提示依赖影响")
    review_parser.add_argument("run_id")
    review_parser.add_argument("--status", choices=sorted(REVIEW_STATES), required=True)
    review_parser.add_argument("--reviewer", required=True)
    review_parser.add_argument("--reason", required=True)
    review_parser.add_argument("--evidence", default="")
    review_parser.add_argument("--scope", default="")
    review_parser.add_argument("--replacement", default="")
    review_parser.add_argument("--dry-run", action="store_true")

    index_parser = subparsers.add_parser("refresh-index", help="从正式元数据重建导航索引")
    index_parser.add_argument("--dry-run", action="store_true")

    context_parser = subparsers.add_parser("build-context", help="构建有界 L0-L2 任务上下文")
    context_parser.add_argument("--project")
    context_parser.add_argument("--module", help="核心算法目录 slug（兼容参数名）；此命令用于导航，不作语义检索")
    context_parser.add_argument("--research")
    context_parser.add_argument("--task", default="")
    context_parser.add_argument("--output", type=Path)
    context_parser.add_argument("--dry-run", action="store_true")

    hash_parser = subparsers.add_parser("hash-file", help="计算文件 SHA-256，便于产物清单引用")
    hash_parser.add_argument("path", type=Path)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 主入口；将预期错误转换成清晰消息和非零退出码。"""

    # memory owns its parser so even unknown options return its structured JSON
    # error contract. argparse.REMAINDER alone still intercepts a leading --help
    # or rejects an unknown option before dispatching to the child parser.
    raw_args = list(sys.argv[1:] if argv is None else argv)
    position, memory_root = 0, None
    if raw_args and raw_args[0] == "--root" and len(raw_args) >= 2:
        memory_root, position = Path(raw_args[1]), 2
    elif raw_args and raw_args[0].startswith("--root="):
        memory_root, position = Path(raw_args[0].split("=", 1)[1]), 1
    if len(raw_args) > position and raw_args[position] == "testing":
        # Dispatch without a shell so task arguments keep their exact boundaries.
        # Explicit roots must identify the target itself, never a parent workspace.
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "testing"))
        import runner as testing_runner
        try:
            testing_root = memory_root.resolve() if memory_root is not None else find_workspace_root(Path.cwd())
            if not (testing_root / "workspace.json").is_file():
                raise FileNotFoundError("显式 --root 必须直接包含 workspace.json")
            result, exit_code = testing_runner.execute(testing_root, raw_args[position + 1:])
        except (OSError, ValueError, RuntimeError) as exc:
            result, exit_code = {"error": str(exc)}, 2
        print(dump_json(result))
        return exit_code
    if len(raw_args) > position and raw_args[position] == "memory":
        from memory import cli as memory_cli
        from memory.errors import MemoryError
        try:
            if memory_root is not None:
                # An explicit target is a boundary, not a starting point for
                # discovery. Walking upward from an incomplete migration
                # target could otherwise publish into an unrelated parent.
                memory_workspace = memory_root.resolve()
                if not (memory_workspace / "workspace.json").is_file():
                    raise FileNotFoundError("显式 --root 必须直接包含 workspace.json；不会回退到上级工作区。")
            else:
                memory_workspace = find_workspace_root(Path.cwd())
            result, exit_code = memory_cli.execute(memory_workspace, raw_args[position + 1:])
        except (MemoryError, OSError, ValueError) as exc:
            result = {"error": exc.as_dict() if isinstance(exc, MemoryError) else
                      {"code": "INVALID_ARGUMENT", "message": str(exc)}, "save_status": "not_committed"}
            exit_code = exc.exit_code if isinstance(exc, MemoryError) else 2
        print(dump_json(result))
        return exit_code

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        explicit_root = getattr(args, "root", None)
        root = find_workspace_root(explicit_root or Path.cwd())

        if args.command == 'workspace-settings':
            import workspace_settings_cli
            result, exit_code = workspace_settings_cli.execute(root, args)
            print(dump_json(result))
            return exit_code

        if args.command == "memory":
            from memory import cli as memory_cli
            result, exit_code = memory_cli.execute(root, args.memory_args)
            print(dump_json(result))
            return exit_code

        if args.command == "material-query":
            from material_query import cli as material_cli
            result, exit_code = material_cli.execute(root, args)
            # Error envelopes deliberately carry value=null. Keep their JSON
            # diagnostics and nonzero exit code when Markdown cannot be produced.
            if getattr(args, 'markdown', False) and (result.get('value') or {}).get('context_markdown'):
                print(result['value']['context_markdown'])
            else:
                print(dump_json(result))
            return exit_code

        if args.command == 'relations':
            from workbench_app import cli as relations_cli
            print(relations_cli.execute(root, args))
            return 0

        if args.command in {'run-register', 'run-execute', 'run-registration-rollback'}:
            import run_capture
            result = run_capture.dispatch(root, args)
            print(dump_json(result))
            return 1 if result.get('execution_status') == 'failed' else 0

        if args.command == "test-data":
            import local_test_data
            print(dump_json(local_test_data.generate(root, preview=args.preview)))
            return 0
        if args.command == "workbench":
            import workbench
            if args.demo:
                import local_test_data
                root = Path(local_test_data.generate(root)["root"])
            workbench.serve(root, args.port, not args.no_browser)
            return 0

        if args.command == "evidence-view":
            import evidence_view
            if args.serve:
                evidence_view.serve(root, args.port)
            else:
                print(dump_json(evidence_view.export(root)))
            return 0
        if args.command == "evidence-monitor":
            import evidence_observer
            result = evidence_observer.monitor(root, args.dry_run)
            print(dump_json(result))
            return 1 if result["errors"] else 0

        if args.command in {"doctor", "verify"}:
            import health
            result = health.doctor(root, args.require, args.smoke) if args.command == "doctor" else health.verify(root, args.profile)
            print(dump_json(result))
            return 0 if result["eligible"] else 1
        if args.command == "evidence-status":
            if args.formal and (not args.target or not args.scope):
                raise ValueError("正式检查需要 target 与 --scope")
            result = evidence_controls.EvidenceGraph(root).status(args.target, args.scope)
            print(dump_json(result))
            return 1 if args.formal and not result.get("eligible", result.get("formal_eligible", False)) else 0
        if args.command == "review-claim":
            print(dump_json(evidence_controls.review_claim(root, args.claim_id, args.status, args.reviewer, args.reason,
                                                 args.evidence, args.scope, args.replacement, args.dry_run)))
            return 0
        if args.command in {"check-run", "finalize-run"}:
            result = (evidence_controls.check_run(root, args.run_id, args.scope) if args.command == "check-run" else
                      evidence_controls.finalize_run(root, args.run_id, args.scope, args.dry_run))
            print(dump_json(result))
            return 0 if result["eligible"] else 1

        if args.command in retrieval.COMMANDS:
            result = retrieval.dispatch(root, args)
            print(dump_json(result))
            manifest = result.get("manifest", {})
            if manifest.get("purpose") == "formal" and not manifest.get("formal_claim_ids"):
                return 1  # 已保留缺失清单；没有正式依据不能冒充生成成功。
            return 0

        if args.command == "validate":
            errors, warnings = validate_workspace(root)
            for warning in warnings:
                print(f"WARNING: {warning}")
            for error in errors:
                print(f"ERROR: {error}")
            if errors:
                print(f"校验失败：{len(errors)} 个错误，{len(warnings)} 个警告。")
                return 1
            print(f"校验通过：0 个错误，{len(warnings)} 个警告。")
            return 0

        if args.command in {"new-core-algorithm", "new-module"}:
            create_module(root, args.slug, args.title, args.dry_run, args.source_document)
        elif args.command == "new-project":
            create_project(root, args.slug, args.title, args.dry_run)
        elif args.command == "new-research":
            create_research(root, args.slug, args.title, args.dry_run)
        elif args.command == "new-run":
            create_run(root, args.project, args.title, args.dry_run, args.keyword, args.module, args.research, args.owner)
        elif args.command == "search-runs":
            print(dump_json(search_runs(root, args.query, args.project, args.limit)))
        elif args.command == "review-run":
            print(dump_json(review_run(root, args.run_id, args.status, args.reviewer, args.reason,
                                       args.evidence, args.scope, args.replacement, args.dry_run)))
        elif args.command == "refresh-index":
            _, warnings = refresh_index(root, args.dry_run)
            for warning in warnings:
                print(f"WARNING: {warning}")
        elif args.command == "build-context":
            build_context(
                root,
                project=args.project,
                module=args.module,
                research=args.research,
                task=args.task,
                output=args.output,
                dry_run=args.dry_run,
            )
        elif args.command == "hash-file":
            target = args.path.resolve()
            if not target.is_file():
                raise FileNotFoundError(f"文件不存在：{target}")
            print(sha256_file(target))
        else:
            parser.error(f"未知命令：{args.command}")
        return 0
    except (OSError, ValueError, KeyError, ImportError, RuntimeError, json.JSONDecodeError, retrieval.sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
