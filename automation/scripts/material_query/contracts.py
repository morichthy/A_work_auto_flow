"""材料查询应用契约；由本模块生成JSON/TS，不改变memory-v3持久化。

只依赖标准库；不可变类型表达请求与回执，不提供返回成功的占位实现。
JSON 中 tuple 对应数组，None 对应 null。运行验证器落实设计CONTRACTS.md
中的范围交集、预算、固定引用和状态约束；类型注解本身不执行这些检查。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, Protocol, TypeAlias, TypeVar

T = TypeVar("T")
Purpose: TypeAlias = Literal["exploration", "formal", "audit"]
RepresentationKey: TypeAlias = Literal["original", "full", "section", "unit_digest", "topic", "domain"]
RelationKind: TypeAlias = Literal["contains", "precedes", "depends_on", "supports", "contradicts", "supersedes", "similar_structure", "member_of", "references", "input", "same_entity", "mentions"]


@dataclass(frozen=True)
class FixedRef:
    """记录必须指定正修订号；文件以登记 source_id 与 SHA256 固定，禁止任意路径。"""
    kind: Literal["record", "file", "owner", "claim", "representation"]
    id: str
    revision: int | None
    sha256: str
    locator: str | None


@dataclass(frozen=True)
class TimeWindow:
    """继承底层按记录、发生、有效时间选择的能力；时间字段与范围独立。"""
    field: Literal["recorded_at", "occurred_at", "valid_at"]
    start_inclusive: str | None
    end_exclusive: str | None


@dataclass(frozen=True)
class Scope:
    """None 不限，空数组无结果；excludes 优先，最终再与可信授权相交。"""
    owner_ids: tuple[str, ...] | None
    levels: tuple[str, ...] | None
    kinds: tuple[str, ...] | None
    roles: tuple[str, ...] | None
    outcomes: tuple[str, ...] | None
    review_states: tuple[str, ...] | None
    validities: tuple[str, ...] | None
    include_unknown: bool
    excluded_refs: tuple[FixedRef, ...]
    excluded_owner_ids: tuple[str, ...]
    recorded_from: str | None
    recorded_before: str | None
    source_ids: tuple[str, ...] | None = None
    include_refs: tuple[FixedRef, ...] = ()
    exclude_ids: tuple[str, ...] = ()
    confidence_levels: tuple[str, ...] | None = None
    time_window: TimeWindow | None = None
    applicability_conditions: tuple[str, ...] = ()
    applicability_exclusions: tuple[str, ...] = ()
    # Owner 类别与记录 kind 是两个独立维度；None 不限，空集合不匹配。
    owner_types: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Budget:
    """均为累计硬上限；wall_ms计各阶段活动墙钟并集，不计用户阅读等待。

    查询TTL独立；毫秒、UTF-8字节、字符分别计量，0禁止该类操作。
    """
    wall_ms: int
    read_bytes: int
    output_chars: int
    candidates: int
    graph_nodes: int
    graph_edges: int
    graph_hops: int
    model_tokens: int
    model_calls: int = 0
    model_input_tokens: int = 0
    model_output_tokens: int = 0
    rerank_items: int = 0


@dataclass(frozen=True)
class Context:
    """仅服务端创建；客户端不能传入授权和剩余预算凭据。"""
    access_handle: str
    budget_handle: str
    cancellation_handle: str


@dataclass(frozen=True)
class Basis:
    refs: tuple[FixedRef, ...]
    owner_heads: tuple[tuple[str, str | None], ...]
    index_watermarks: tuple[tuple[str, str], ...]
    consistency: Literal["fixed_refs", "single_owner_snapshot", "cross_owner_optimistic"]
    basis_id: str = ""
    observed_at: str = ""


@dataclass(frozen=True)
class Issue:
    """机器可判读的局部问题；affected_refs 只含已授权且已固定的对象。"""
    code: str
    message: str
    affected_refs: tuple[FixedRef, ...]
    retry: Literal["never", "same_request", "replan", "after_external_change"]


@dataclass(frozen=True)
class Result(Generic[T]):
    """partial 仍可有内容；拒绝时不得返回未授权对象的标题、数量或定位信息。"""
    status: Literal["ok", "partial", "rejected", "cancelled", "failed"]
    value: T | None
    code: str | None
    warnings: tuple[str, ...]
    consumed: Budget
    stop_reason: str | None
    basis: Basis | None
    issues: tuple[Issue, ...] = ()


@dataclass(frozen=True)
class DefinitionRef:
    key: RepresentationKey
    version: str


@dataclass(frozen=True)
class FieldRule:
    """选择既有字段；字段选择器只允许注册值，不接受 Python/SQL 表达式。"""
    section_name: str
    selectors: tuple[str, ...]
    required: bool
    relations: tuple[RelationKind, ...]


@dataclass(frozen=True)
class RepresentationDefinition:
    ref: DefinitionRef
    title: str
    purpose_description: str
    rules: tuple[FieldRule, ...]
    output_sections: tuple[str, ...]
    generation: Literal["never", "draft_only"]


@dataclass(frozen=True)
class Realization:
    """一组固定材料按某版类型可提供的内容，和不依赖材料的类型定义分开。"""
    definition: DefinitionRef
    refs: tuple[FixedRef, ...]
    state: Literal["direct", "assemblable", "needs_generation", "stale", "unsupported"]
    missing_selectors: tuple[str, ...]
    generator_version: str | None


@dataclass(frozen=True)
class AssociationOptions:
    mode: Literal["off", "existing_only", "explore_structural"]
    strategy: str
    strategy_version: str
    max_items: int
    output_share: float
    supplement_scope: Scope | None


@dataclass(frozen=True)
class QueryRequest:
    definition: DefinitionRef
    question: str
    keywords: tuple[str, ...]
    scope: Scope
    scope_ceiling: Scope
    purpose: Purpose
    association: AssociationOptions
    budget: Budget
    freshness: Literal["fixed", "current", "allow_stale"]
    result_limit: int
    missing_policy: Literal["reject", "skip", "fallback"]
    fallback_definitions: tuple[DefinitionRef, ...]
    applicability: str
    channels: tuple[Literal["identity", "lexical", "dense", "sparse", "graph"], ...] = ("identity", "lexical")
    dialect: Literal["plain", "phrase", "boolean"] = "plain"
    ranking_strategy: str = "topic-evidence-v2"
    ranking_version: str = "1"
    allow_index_repair: bool = False
    max_staleness_seconds: float | None = None
    # None 保留旧表示查询；主入口按规范内容种类召回，与访问范围分开。
    content_source: Literal['overview_experience', 'process', 'technical', 'all'] | None = None


@dataclass(frozen=True)
class ContentExpandRequest:
    """只展开服务器已经交付的候选，不接受客户端构造任意引用。"""
    query_id: str
    candidate_ids: tuple[str, ...]
    target: Literal['process', 'technical']
    expected_request_digest: str
    # 显式请求一并读取展开正文、必要依赖和已启用的补充；旧调用仍只返候选。
    include_packet: bool = False


@dataclass(frozen=True)
class FullDocumentsRequest:
    """从已选命中定位既有文稿，禁止客户端指定任意未召回记录。"""
    query_id: str
    candidate_ids: tuple[str, ...]
    expected_request_digest: str
    document_type: Literal['research_process', 'research_report'] = 'research_process'


@dataclass(frozen=True)
class ChannelHit:
    """保留独立通道诊断；分数含义由策略说明，不充当知识置信度。"""
    channel: str
    provider: str
    provider_version: str
    rank: int
    raw_score: float | None
    score_meaning: str
    representation_refs: tuple[FixedRef, ...]
    # 只交付已授权固定命中的实际片段；正式用途未经逐 claim 准入时留空。
    matched_text: str | None = None


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    refs: tuple[FixedRef, ...]
    title: str
    excerpt: str
    channels: tuple[str, ...]
    score: float
    realization: Realization
    evidence_status: str
    group: Literal["direct", "required_context", "association"]
    hits: tuple[ChannelHit, ...] = ()
    evaluated_claim_refs: tuple[FixedRef, ...] = ()
    unresolved_claim_refs: tuple[FixedRef, ...] = ()
    # 明示缺少的分类维度；include_unknown 只改变准入，不把未知改成已分类。
    unknown_facets: tuple[str, ...] = ()
    content_kind: str | None = None
    knowledge_type: Literal["observation", "conclusion", "hypothesis", "recommendation"] | None = None
    is_latest: bool | None = None
    owner_type: str | None = None


@dataclass(frozen=True)
class DiscoveryReadiness:
    status: Literal["ready", "unavailable", "incomplete", "insufficient"]
    reasons: tuple[str, ...]
    projection_version: str | None = None


@dataclass(frozen=True)
class OwnerScreeningWindow:
    text: str
    refs: tuple[FixedRef, ...]
    projection_id: str | None = None
    source_level: str | None = None
    source_kind: str | None = None
    channels: tuple[str, ...] = ()
    locator: str | None = None
    matched_protected_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class OwnerScreeningCoverage:
    complete: bool
    gaps: tuple[str, ...]


@dataclass(frozen=True)
class OwnerAssessment:
    owner_id: str
    status: Literal["relevant", "uncertain", "irrelevant"]
    reason: str
    packet_digest: str


@dataclass(frozen=True)
class OwnerAssessmentBatchRequest:
    """CAS mutation over the exact screening packets already delivered by one RS."""
    session_id: str
    expected_revision: int
    request_id: str
    assessments: tuple[OwnerAssessment, ...]


@dataclass(frozen=True)
class OwnerFulltextRecallRequest:
    """Explicit user-selected compensation; query/scope remain frozen in the RS."""
    session_id: str
    expected_revision: int
    request_id: str


@dataclass(frozen=True)
class OwnerScreeningPacket:
    owner_id: str
    windows: tuple[OwnerScreeningWindow, ...]
    coverage: OwnerScreeningCoverage
    packet_digest: str
    retrieval_source: Literal["discovery", "fulltext_compensation"]
    title: str | None = None
    overview: str | None = None
    assessment: OwnerAssessment | None = None


@dataclass(frozen=True)
class OwnerRecallReceipt:
    owner_packets: tuple[OwnerScreeningPacket, ...]
    discovery: DiscoveryReadiness
    fulltext_compensation_available: bool
    fulltext_compensation_reason: str
    next_action: str


@dataclass(frozen=True)
class OwnerAssessmentReceipt:
    session_id: str
    revision: int
    assessments: tuple[OwnerAssessment, ...]
    relevant_owner_ids: tuple[str, ...]
    next_action: Literal["synthesize", "read", "page"]
    fulltext_compensation_available: bool
    fulltext_compensation_reason: str
    gaps: tuple[str, ...]


@dataclass(frozen=True)
class SearchReceipt:
    query_id: str
    request_digest: str
    candidates: tuple[Candidate, ...]
    next_cursor: str | None
    expires_at: str
    gaps: tuple[str, ...]


@dataclass(frozen=True)
class QueryJob:
    """首次搜索先返回可取消身份；poll读取同一操作，不能重复执行/计费。"""
    query_id: str
    state: Literal["running", "completed", "cancelled", "failed"]


@dataclass(frozen=True)
class AssembleRequest:
    query_id: str
    candidate_ids: tuple[str, ...]
    expected_request_digest: str


@dataclass(frozen=True)
class PacketFigure:
    index: int
    caption: str
    ref: FixedRef
    data_url: str


@dataclass(frozen=True)
class AssemblyPart:
    group: Literal["direct", "required_context", "association", "gaps"]
    heading: str
    markdown: str
    refs: tuple[FixedRef, ...]
    selectors: tuple[str, ...]
    omitted: tuple[str, ...]
    figures: tuple[PacketFigure, ...] = ()


@dataclass(frozen=True)
class DocumentMatch:
    ref: FixedRef
    title: str
    candidate_ids: tuple[str, ...]
    complete: bool
    part_indices: tuple[int, ...] = ()


@dataclass(frozen=True)
class MaterialPacket:
    packet_id: str
    query_id: str
    definition: DefinitionRef
    parts: tuple[AssemblyPart, ...]
    contributors: tuple[FixedRef, ...]
    complete: bool
    canonical: bool
    documents: tuple[DocumentMatch, ...] = ()


@dataclass(frozen=True)
class StructuralProfile:
    refs: tuple[FixedRef, ...]
    problem: str
    variable_roles: tuple[str, ...]
    mechanism: str
    constraints: tuple[str, ...]
    intervention: str
    outcome_conditions: tuple[str, ...]
    author: str
    generator_version: str


@dataclass(frozen=True)
class AssociationProposal:
    proposal_id: str
    source: tuple[FixedRef, ...]
    target: tuple[FixedRef, ...]
    common_structure: str
    differences: tuple[str, ...]
    transfer_conditions: tuple[str, ...]
    verification_hint: str
    method: str
    state: Literal["temporary", "accepted_navigation", "rejected", "stale"]


@dataclass(frozen=True)
class AssociationRequest:
    query_id: str
    seed_candidate_ids: tuple[str, ...]
    profile: StructuralProfile | None


@dataclass(frozen=True)
class GraphEdge:
    edge_id: str
    source: FixedRef
    target: FixedRef
    kind: RelationKind
    evidence: tuple[FixedRef, ...]
    state: Literal["proposed", "accepted_navigation", "verified_claim", "stale", "retracted"]
    conditions: tuple[str, ...]
    differences: tuple[str, ...]
    proposer: str
    generator_version: str
    # 固定证据身份不携带关系。与 evidence 按序对应，避免把出处引用误作支持。
    evidence_relations: tuple[RelationKind, ...] = ()
    # 保存规范关系的原字段/名称；旧别名转换可审计，不能只留下显示分类。
    legacy_relation: str | None = None


@dataclass(frozen=True)
class DeepenRequest:
    query_id: str
    candidate_ids: tuple[str, ...]
    mode: Literal["source_mapping", "bounded_graph", "structural_discovery"]
    relation_kinds: tuple[RelationKind, ...]
    direction: Literal["forward", "reverse", "both"]
    strategy: str
    strategy_version: str
    cursor: str | None


@dataclass(frozen=True)
class DeepenReceipt:
    candidates: tuple[Candidate, ...]
    edges: tuple[GraphEdge, ...]
    proposals: tuple[AssociationProposal, ...]
    next_cursor: str | None
    gaps: tuple[str, ...]
    packet: MaterialPacket | None = None


@dataclass(frozen=True)
class MaintenanceRequest:
    changed_refs: tuple[FixedRef, ...]
    scope: Scope
    strategy: str
    strategy_version: str


@dataclass(frozen=True)
class MaintenanceItem:
    ref: FixedRef
    action: Literal["retain", "revise", "resynthesize", "retract", "defer"]
    reasons: tuple[str, ...]
    affected_refs: tuple[FixedRef, ...]
    draft_json: str | None  # 按现有 memory-v3 schema 预检，不是任意可执行命令。


@dataclass(frozen=True)
class MaintenancePlan:
    plan_id: str
    plan_digest: str
    basis: Basis
    items: tuple[MaintenanceItem, ...]
    reviewed_refs: tuple[FixedRef, ...]
    unchecked_regions: tuple[str, ...]
    semantic_reviewer: str | None
    context_items: tuple[AssemblyPart, ...] = ()
    read_receipt: str | None = None
    review_note: str = ""
    reviewer_kind: Literal["human", "ai"] | None = None


@dataclass(frozen=True)
class MaintenanceReceipt:
    commits: tuple[tuple[str, str], ...]
    pending_items: tuple[str, ...]
    index_status: Literal["indexed", "pending", "failed"]
    recovery_receipt: str | None


@dataclass(frozen=True)
class MaintenanceStatusRequest:
    """重启后用新的可信 query 重新授权一个持久 plan_id。"""
    query_id: str
    plan_id: str


@dataclass(frozen=True)
class MaintenanceVersionStatus:
    plan_digest: str
    parent_digest: str | None
    reviewed: bool
    leaf: bool
    item_count: int


@dataclass(frozen=True)
class MaintenanceCommittedChange:
    ref: FixedRef
    content_hash: str
    client_key: str | None
    status: Literal["created", "updated", "no_change"]


@dataclass(frozen=True)
class MaintenanceCommitStatus:
    """由规范 request ledger 核实的提交，单独保留原回执指纹。"""
    request_id: str
    owner_id: str
    commit_id: str
    generation: int
    save_status: Literal["committed", "no_change"]
    changes: tuple[MaintenanceCommittedChange, ...]
    receipt_sha256: str


@dataclass(frozen=True)
class MaintenanceReviewStatus:
    ref: FixedRef
    review_state: Literal["not-assessed", "not-reviewed", "accepted", "disputed", "retracted", "superseded"]
    validity: Literal["valid", "invalid", "unknown"]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class MaintenanceIndexStatus:
    owner_id: str
    head: str | None
    target_generation: int
    indexed_generation: int | None
    vector_generation: int | None
    fts_status: Literal["indexed", "pending", "failed"]
    vector_status: Literal["indexed", "pending", "failed", "disabled"]
    coverage: Literal["complete", "partial"]


@dataclass(frozen=True)
class MaintenanceAttemptStatus:
    request_id: str
    plan_digest: str
    state: Literal["started", "partial", "committed", "no_changes"]
    completed_owner_ids: tuple[str, ...]
    pending_owner_ids: tuple[str, ...]
    local_receipt_owner_ids: tuple[str, ...]
    local_completed: bool
    recovery_receipt: str


@dataclass(frozen=True)
class MaintenanceStatusReceipt:
    """只读维护状态；不会推进下一步或隐式选择审查版本分支。"""
    plan_id: str
    plan_versions: tuple[MaintenanceVersionStatus, ...]
    commits: tuple[MaintenanceCommitStatus, ...]
    pending_owner_ids: tuple[str, ...]
    pending_items: tuple[str, ...]
    review_states: tuple[MaintenanceReviewStatus, ...]
    pending_reviews: tuple[FixedRef, ...]
    index_states: tuple[MaintenanceIndexStatus, ...]
    attempts: tuple[MaintenanceAttemptStatus, ...]
    resume_cursor: str | None
    basis_stale: bool


@dataclass(frozen=True)
class TreeRequest:
    scope: Scope
    parent_ref: FixedRef | None
    cursor: str | None
    limit: int
    view: Literal["logical", "storage"]
    parent_node_id: str | None = None  # 逻辑owner/层级无内容Ref，用服务端结构节点身份分页。
    owner_query: str = ""  # 只筛选获准对象的标题/身份；不是任意路径搜索。


@dataclass(frozen=True)
class TreeNode:
    ref: FixedRef | None
    node_id: str
    parent_id: str | None
    title: str
    kind: str
    layer: str | None
    has_children: bool
    storage_role: Literal["canonical", "source_reference", "projection", "temporary"]
    registered_path: str | None
    owner_type: str | None = None


@dataclass(frozen=True)
class TreePage:
    nodes: tuple[TreeNode, ...]
    next_cursor: str | None


class Definitions(Protocol):
    def list(self, ctx: Context) -> Result[tuple[RepresentationDefinition, ...]]: ...
    def get(self, ref: DefinitionRef, ctx: Context) -> Result[RepresentationDefinition]: ...


class Realizations(Protocol):
    def inspect(self, refs: tuple[FixedRef, ...], definition: DefinitionRef, ctx: Context) -> Result[tuple[Realization, ...]]: ...


class QueryCoordinator(Protocol):
    def start(self, request: QueryRequest, ctx: Context) -> Result[QueryJob]: ...
    def poll(self, query_id: str, ctx: Context) -> Result[SearchReceipt]: ...
    def search(self, request: QueryRequest, ctx: Context) -> Result[SearchReceipt]: ...
    def assemble(self, request: AssembleRequest, ctx: Context) -> Result[MaterialPacket]: ...
    def resume(self, query_id: str, cursor: str, ctx: Context) -> Result[SearchReceipt]: ...
    def cancel(self, query_id: str, ctx: Context) -> Result[None]: ...


class AssociationStrategy(Protocol):
    def discover(self, request: AssociationRequest, ctx: Context) -> Result[tuple[AssociationProposal, ...]]: ...
    def decide(self, query_id: str, proposal_id: str, decision: Literal["accept_navigation", "reject"], reason: str, request_id: str, ctx: Context) -> Result[AssociationProposal]: ...


class DeepeningStrategy(Protocol):
    def deepen(self, request: DeepenRequest, ctx: Context) -> Result[DeepenReceipt]: ...


class SemanticMaintenance(Protocol):
    def plan(self, request: MaintenanceRequest, ctx: Context) -> Result[MaintenancePlan]: ...
    def review(self, plan: MaintenancePlan, expected_digest: str, ctx: Context) -> Result[MaintenancePlan]: ...
    def apply(self, plan_id: str, expected_digest: str, request_id: str, ctx: Context) -> Result[MaintenanceReceipt]: ...
    def status(self, plan_id: str, ctx: Context) -> Result[MaintenanceStatusReceipt]: ...


class StructureView(Protocol):
    def list_page(self, request: TreeRequest, ctx: Context) -> Result[TreePage]: ...
