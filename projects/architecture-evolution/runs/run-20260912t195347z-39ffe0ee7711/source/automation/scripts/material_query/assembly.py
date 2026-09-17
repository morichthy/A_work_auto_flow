"""按已选固定材料组包；只做模板和已登记依赖展开，不隐式二次检索。

正文按完整块原子加入，预算不足时省略并明确缺口，不从公式/定义中间截断。
新领域解释不在这里生成，更不会由一次查询隐式提交规范记录。
"""
from dataclasses import asdict
import base64
import json
import re

from memory.technical_units import description_text, is_unit, render_full
from memory.errors import MemoryError

from .contracts import FixedRef
from .legacy_adapter import fixed_record, to_legacy, memory_error
from .validation import QueryError, parse


def _text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join("- " + _text(item) for item in value)
    return json.dumps(value, ensure_ascii=False, indent=2)


def readable_payload(payload):
    """只模板呈现既有语义字段，隐藏内部版本引用JSON到来源栏。"""
    keys = ("question", "problem", "problem_structure", "action", "observation", "decision", "recommendation", "applicability",
            "applicable", "prohibited", "retry_conditions", "conditions", "limitations", "failure_modes", "summary", "overview", "next_steps", "purpose", "scope")
    return "\n\n".join(f"**{key}**\n\n{_text(payload[key])}" for key in keys if payload.get(key))


def legacy_full(record):
    """Preserve every legacy semantic field, including formulas and units.

    Version-two details keep scientific content outside body_markdown. Treating
    the body as the full record silently loses method/parameters/results. Known
    formula fields receive readable LaTeX; other saved fields remain explicit.
    """
    payload = record["payload"]
    labels = {"question": "问题", "method": "方法", "steps": "步骤", "parameters": "参数与单位", "results": "结果",
              "limitations": "限制", "inputs": "固定输入", "run_ref": "依据Run", "claims": "结论及适用范围",
              "applicable": "适用条件", "prohibited": "不适用条件", "failure_modes": "失败模式", "recommendation": "建议"}
    parts = [record.get("body_markdown", "")]
    for key, value in payload.items():
        if value is None or value == [] or value == "":
            continue
        if key == "formulas":
            for formula in value:
                variables = "\n".join("- $" + v["symbol"] + "$：" + v["meaning"] + "；单位：" + v["unit"] for v in formula["variables"])
                parts.append("$$\n" + formula["latex"] + "\n$$\n\n" + variables)
        else:
            parts.append("**" + labels.get(key, key) + "**\n\n" + _text(value))
    return "\n\n".join(part for part in parts if part)


def required_block_ids(record, selected):
    blocks = {b["block_id"]: b for b in record["payload"].get("blocks", [])}
    pending, seen = list(selected), set()
    while pending:
        bid = pending.pop()
        if bid in seen:
            continue
        if bid not in blocks:
            raise QueryError("SOURCE_MISSING", "技术块缺少必需定义")
        seen.add(bid)
        pending.extend(blocks[bid].get("requires_block_ids", []))
    return seen


def content_parts(record, ref, definition, question=""):
    """返回(group,title,text,selector,ref)列表，外层负责预算与来源权限。"""
    key, payload = definition.key, record["payload"]
    if record["kind"] == "representation" and key == "full":
        return [("direct", record["title"], payload.get("text", ""), "representation.text", ref)]
    if record.get("schema_version") == 4 and key in {"full", "section"}:
        # Narrative/overview/experience v4 require an authored complete body.
        # Structured navigation metadata stays inspectable on the record; it
        # must not be appended as a second prose source or exposed as raw JSON.
        return [("direct", record["title"], record["body_markdown"], "body_markdown", ref)]
    if key == "unit_digest":
        text = description_text(record) if is_unit(record) else readable_payload(payload)
        return [("direct", record["title"], text, "detail.retrieval_description" if is_unit(record) else "experience", ref)]
    if is_unit(record):
        blocks = payload["blocks"]
        if key == "section":
            locator = ref.locator or ""
            if locator.startswith("block:"):
                selected = {locator[6:]}
            else:
                terms = [term for term in re.split(r"\s+", question) if term]
                selected = {b["block_id"] for b in blocks if any(term.casefold() in b["markdown"].casefold() for term in terms)}
                if not selected:
                    raise QueryError("SOURCE_MISSING", "未定位到相关技术块；请提供匹配关键词或显式block定位")
            required = required_block_ids(record, selected)
            return [("direct" if b["block_id"] in selected else "required_context", b.get("title", b["block_id"]), b["markdown"],
                     "detail.blocks." + b["block_id"], fixed_record(record, "block:" + b["block_id"]))
                    for b in blocks if b["block_id"] in required]
        return [("direct", record["title"], render_full(record), "detail.blocks", ref)]
    if record["kind"] == "document_section":
        return [("direct", payload.get("title", record["title"]), b["markdown"], "document_section.blocks", ref)
                for b in payload.get("blocks", []) if b["type"] == "prose"]
    return [("direct", record["title"], legacy_full(record), record["kind"], ref)]


class Assembler:
    def __init__(self, reader, ledger, allowed, *, required_allowed=None, association_allowed=None, purpose="exploration", formal_texts=None, association_share=1.0):
        self.reader, self.ledger, self.allowed = reader, ledger, allowed
        self.required_allowed = required_allowed or allowed
        self.association_allowed = association_allowed or allowed
        self.purpose = purpose
        self.formal_texts = formal_texts or {}
        self.parts, self.gaps, self.contributors = [], [], {}
        self.issues = []
        self.visited = set()
        self.association_limit = int(ledger.remaining("output_chars") * association_share)
        self.association_used = 0

    def gap(self, message, *, code="SOURCE_MISSING", ref=None):
        """引用仅在 Reader 已完成授权固定读取后附加，未知来源只报告局部缺口。"""
        from .coordinator import retry_hint
        known = ref is not None and any(item.id == ref.id and item.revision == ref.revision and item.sha256 == ref.sha256
                                       for item in self.reader.fixed.values())
        self.gaps.append(message)
        self.issues.append({"code": code, "message": message,
                            "affected_refs": [asdict(ref)] if known and code != "DENIED" else [], "retry": retry_hint(code)})

    def add(self, group, title, text, selector, ref, *, figures=()):
        # 多个命中块可能共享同一定义。按固定引用与选择器去重，避免重复
        # 输出/计费；若该定义本身也是命中，将其从必要上下文提升为直接项。
        fixed = asdict(ref)
        for existing in self.parts:
            if existing['refs'] == [fixed] and existing['selectors'] == [selector] and existing['markdown'] == text:
                if group == 'direct':
                    existing['group'] = 'direct'
                return
        if not text:
            self.gap("选定材料没有可组合正文", ref=ref)
            return
        if group == "association" and self.association_used + len(text) > self.association_limit:
            self.gap("联想补充达到篇幅比例上限，已省略完整块", code="BUDGET", ref=ref)
            return
        if len(text) > self.ledger.remaining("output_chars"):
            self.gap("输出预算不足，已省略完整块：" + title, code="BUDGET", ref=ref)
            return
        self.ledger.charge("output_chars", len(text))
        if group == "association":
            self.association_used += len(text)
        part = {"group": group, "heading": title, "markdown": text,
                "refs": [asdict(ref)], "selectors": [selector], "omitted": []}
        self.parts.append(part)
        self.contributors[(ref.id, ref.revision, ref.sha256)] = ref
        # 图片随本次已授权材料包返回，避免浏览器另开不带原范围/预算的读取。
        # 二进制按 read_bytes 计量；output_chars 计正文及图注，不计传输编码。
        for number, figure in enumerate(figures):
            if selector.startswith("detail.blocks.") and f"](figure:{number})" not in text:
                continue
            legacy = figure["ref"]
            image_ref = FixedRef(legacy["target_kind"], legacy["target_id"], legacy["revision"], legacy["sha256"], legacy["locator"])
            try:
                if image_ref.kind != "file":
                    raise QueryError("SOURCE_MISSING", "图示没有已登记文件引用")
                path, _ = self.reader.service._file(to_legacy(image_ref))
                if not path.is_relative_to(self.reader.root) or path.stat().st_size > 8 * 1024 * 1024:
                    raise QueryError("DENIED", "图示不属于工作区受控附件或超过8 MiB展示上限")
                raw = self.reader.file_bytes(image_ref)
                mime = ("image/png" if raw.startswith(b"\x89PNG\r\n\x1a\n") else
                        "image/jpeg" if raw.startswith(b"\xff\xd8\xff") else
                        "image/webp" if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP" else None)
                if mime is None:
                    raise QueryError("SOURCE_MISSING", "图示不是可展示的固定栅格图片")
                self.ledger.charge("output_chars", len(figure["caption"]))
                part.setdefault("figures", []).append({"index": number, "caption": figure["caption"], "ref": asdict(image_ref),
                    "data_url": "data:" + mime + ";base64," + base64.b64encode(raw).decode("ascii")})
                if selector == "detail.blocks" and f"](figure:{number})" not in part["markdown"]:
                    # 完整单元中尚未安置的已登记图，按原图序追加；局部块不
                    # 追加其他图，避免把块外材料混入显式片段选择。
                    marker = f"\n\n![图{number + 1}](figure:{number})"
                    self.ledger.charge("output_chars", len(marker))
                    part["markdown"] += marker
                self.contributors[(image_ref.id, image_ref.revision, image_ref.sha256)] = image_ref
            except (QueryError, MemoryError) as exc:
                exc = memory_error(exc) if isinstance(exc, MemoryError) else exc
                if exc.code in {"BUDGET", "CANCELLED"}:
                    raise
                self.gap(exc.message, code=exc.code, ref=image_ref)

    def add_record(self, ref, definition, question, *, group=None):
        identity = (ref.id, ref.revision, ref.sha256, ref.locator, definition.key)
        if identity in self.visited:
            return
        self.visited.add(identity)
        self.ledger.checkpoint()
        if ref.kind == "file":
            self.add(group or "direct", "原始材料", self.reader.file(ref), "source.content", ref)
            return
        if ref.kind == "owner":
            # Owner 原件由候选准入和缓存回读核验范围；它仍是 L0，不提升为结论。
            text, _native = self.reader.native(ref)
            self.add(group or "direct", "原始登记", text, "owner.native", ref)
            return
        record = self.reader.record(ref)
        payload = record["payload"]
        check = self.required_allowed if group == "required_context" else self.association_allowed if group == "association" else self.allowed
        if not check(record):
            self.gap("必要内容被当前范围排除", code="DENIED")
            return
        from .representations import availability
        if availability(record, ref, definition)["state"] not in {"direct", "assemblable"}:
            self.gap("选定材料缺少请求表示；需要显式生成或选择允许的回退类型", ref=ref)
            return
        if self.purpose == "formal":
            # Formal projection text is supplied only after fresh per-claim
            # evidence assessment; arbitrary record prose never enters support.
            text = self.formal_texts.get(ref.id)
            if text:
                self.add(group or "direct", record["title"], text, "verified_claims", ref)
            else:
                self.gap("选定内容没有符合当前适用范围的已复核结论", code="STALE", ref=ref)
            return
        if definition.key == "original":
            sources = [item for item in record["sources"] if item["target_kind"] == "file"]
            if not sources:
                self.gap("选定材料没有可读的已登记原件", ref=ref)
            for item in sources:
                target = FixedRef("file", item["target_id"], item["revision"], item["sha256"], item["locator"])
                self.add(group or "direct", record["title"] + "：原始材料", self.reader.file(target), "source.content", target)
            return
        # 独立文稿只返回编排正文，不把 section_refs 等内部 JSON 拼成正文。
        # 章节的 prose/unit 必须保持作者顺序，不能先收集全部 prose 再接技术块。
        if record["kind"] not in {"document", "document_section"}:
            for part_group, title, text, selector, part_ref in content_parts(record, ref, definition, question):
                self.add(group or part_group, title, text, selector, part_ref,
                         figures=payload.get("figures", ()) if record["kind"] == "detail" else ())
        elif record["kind"] == "document_section":
            from .contracts import DefinitionRef
            from dataclasses import replace
            for position, block in enumerate(record["payload"].get("blocks", [])):
                if block["type"] == "prose":
                    self.add(group or "direct", record["payload"].get("title", record["title"]),
                             block["markdown"], "document_section.blocks." + str(position), ref)
                else:
                    target = block["ref"]
                    child = FixedRef("record", target["target_id"], target["revision"], target["sha256"], target["locator"])
                    try:
                        for bid in block.get("block_ids", []) or [None]:
                            self.add_record(replace(child, locator="block:" + bid) if bid else child,
                                            DefinitionRef("section" if bid else "full", "1"), question, group=group)
                    except QueryError as exc:
                        if exc.code in {"BUDGET", "CANCELLED"}:
                            raise
                        self.gap(exc.message, code=exc.code, ref=child)
        payload = record["payload"]
        references = []
        if record["kind"] == "document":
            references = payload.get("section_refs", [])
        elif record["kind"] == "map" and definition.key in {"topic", "domain"}:
            references = payload.get("result_refs", [])
        # Prerequisite records are required reading, not optional association
        # supplements. Keep them explicit in the packet or report their gap.
        references = [*references, *(item for item in record["sources"] if item.get("relation") == "prerequisite")]
        for target in references:
            if target["target_kind"] != "record" or not target.get("sha256"):
                self.gap("引用缺少可直接读取的固定记录身份", ref=ref)
                continue
            # Authored document order stays stable; all dependencies remain under
            # original selection/ceiling/exclusions and the same cumulative ledger.
            child = FixedRef("record", target["target_id"], target["revision"], target["sha256"], target["locator"])
            from .contracts import DefinitionRef
            child_def = DefinitionRef("full" if definition.key in {"full", "section"} else "unit_digest", "1")
            if record["kind"] == "document" and definition.key in {"topic", "domain"}:
                child_def = DefinitionRef(definition.key, "1")
            try:
                if target.get("_block_ids"):
                    # Authored section selection is an explicit content boundary;
                    # keep selected block IDs and only add their prerequisites.
                    from dataclasses import replace
                    for block_id in target["_block_ids"]:
                        self.add_record(replace(child, locator="block:" + block_id), DefinitionRef("section", "1"), question, group="required_context")
                else:
                    self.add_record(child, child_def, question,
                                    group=(group or "direct") if record["kind"] == "document" and target in payload.get("section_refs", []) else "required_context")
            except QueryError as exc:
                if exc.code in {"BUDGET", "CANCELLED"}:
                    raise
                self.gap(exc.message, code=exc.code, ref=child)
