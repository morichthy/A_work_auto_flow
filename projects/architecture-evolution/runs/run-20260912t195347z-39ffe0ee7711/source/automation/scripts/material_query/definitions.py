"""版本化表示规则；列举规则不扫描材料，不要求另外保存摘要文件。"""
from dataclasses import asdict

from .contracts import DefinitionRef, FieldRule, RepresentationDefinition
from .validation import QueryError, object_fields


VERSION = "1"
# Version the compatibility table independently of the actual definitions.
# Explicit source/target versions prevent a legacy request from silently moving
# to a different recipe when a future release adds or renames a definition.
LEGACY_ALIAS_VERSION = "1"
LEGACY_ALIASES = {"original": "original", "full": "full", "section": "section",
                  "unit_digest": "unit_digest", "topic_synthesis": "topic", "domain_synthesis": "domain"}
_ROWS = (
    ("original", "原始材料", "已登记L0原件或固定受控摘录", ("source.content",), ("原始材料", "来源与缺口"), "never"),
    ("full", "完整研究内容", "技术单元全文或研究过程文稿，保留定义与限制", ("detail.blocks", "document.sections"), ("完整正文", "必要上下文", "来源与缺口"), "never"),
    ("section", "相关章节与技术块", "选定章节/技术块及其必需定义", ("detail.blocks", "document_section.content"), ("相关内容", "必要定义", "来源与缺口"), "never"),
    ("unit_digest", "单元摘要", "已有检索说明或经验结构字段的模板组合", ("detail.retrieval_description", "experience.recommendation", "experience.applicability"), ("问题", "方法与结果", "限制", "来源与缺口"), "never"),
    ("topic", "主题材料", "主题地图、已有简报与明确关联的限制/反证", ("map", "document.sections"), ("主题内容", "差异与限制", "来源与缺口"), "draft_only"),
    ("domain", "领域材料", "选定主题并列组合；新的统一解释需要审查", ("map", "document.sections"), ("逐主题材料", "差异与限制", "来源与缺口"), "draft_only"),
)
DEFINITIONS = {
    key: RepresentationDefinition(DefinitionRef(key, VERSION), title, purpose,
        (FieldRule(sections[0], selectors, True, ("contains", "depends_on")),), sections, generation)
    for key, title, purpose, selectors, sections, generation in _ROWS
}


def get(ref):
    if ref.key not in DEFINITIONS or ref.version != VERSION:
        raise QueryError("UNSUPPORTED", "表示类型或版本未注册")
    return DEFINITIONS[ref.key]


def listing():
    return [asdict(item) for item in DEFINITIONS.values()]


def resolve_legacy(raw):
    """Resolve one old key as a pure, explicit pre-step to a new query.

    No material is scanned or built. Resolving a name grants neither fallback
    permission nor semantic generation/commit permission; the returned target
    must still pass the normal query and definition capability checks.
    """
    object_fields(raw, {"source_contract_version", "key", "target_definition_version"})
    if any(not isinstance(raw[name], str) or not raw[name] for name in raw):
        raise QueryError("VALIDATION", "表示别名必须给出明确的字符串名称与版本")
    if raw["source_contract_version"] != "0.1" or raw["target_definition_version"] != VERSION:
        raise QueryError("UNSUPPORTED", "该旧契约/目标定义版本没有登记的名称映射")
    key = LEGACY_ALIASES.get(raw["key"])
    if key is None:
        raise QueryError("UNSUPPORTED", "旧表示名称未登记；不猜测相似名称或回退配方")
    definition = get(DefinitionRef(key, VERSION))
    return {"source_contract_version": "0.1", "source_key": raw["key"],
            "mapping_version": LEGACY_ALIAS_VERSION, "definition": asdict(definition.ref),
            "generation": definition.generation, "canonical": False}
