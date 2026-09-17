// Generated from material_query/contracts.py; do not edit.
export interface FixedRef {
  kind: "record" | "file" | "owner" | "claim" | "representation";
  id: string;
  revision: number | null;
  sha256: string;
  locator: string | null;
}

export interface TimeWindow {
  field: "recorded_at" | "occurred_at" | "valid_at";
  start_inclusive: string | null;
  end_exclusive: string | null;
}

export interface Scope {
  owner_ids: Array<string> | null;
  levels: Array<string> | null;
  kinds: Array<string> | null;
  roles: Array<string> | null;
  outcomes: Array<string> | null;
  review_states: Array<string> | null;
  validities: Array<string> | null;
  include_unknown: boolean;
  excluded_refs: Array<FixedRef>;
  excluded_owner_ids: Array<string>;
  recorded_from: string | null;
  recorded_before: string | null;
  source_ids?: Array<string> | null;
  include_refs?: Array<FixedRef>;
  exclude_ids?: Array<string>;
  confidence_levels?: Array<string> | null;
  time_window?: TimeWindow | null;
  applicability_conditions?: Array<string>;
  applicability_exclusions?: Array<string>;
  owner_types?: Array<string> | null;
}

export interface Budget {
  wall_ms: number;
  read_bytes: number;
  output_chars: number;
  candidates: number;
  graph_nodes: number;
  graph_edges: number;
  graph_hops: number;
  model_tokens: number;
  model_calls?: number;
  model_input_tokens?: number;
  model_output_tokens?: number;
  rerank_items?: number;
}

export interface Context {
  access_handle: string;
  budget_handle: string;
  cancellation_handle: string;
}

export interface Basis {
  refs: Array<FixedRef>;
  owner_heads: Array<[string, string | null]>;
  index_watermarks: Array<[string, string]>;
  consistency: "fixed_refs" | "single_owner_snapshot" | "cross_owner_optimistic";
  basis_id?: string;
  observed_at?: string;
}

export interface Issue {
  code: string;
  message: string;
  affected_refs: Array<FixedRef>;
  retry: "never" | "same_request" | "replan" | "after_external_change";
}

export interface Result<T = unknown> {
  status: "ok" | "partial" | "rejected" | "cancelled" | "failed";
  value: T | null;
  code: string | null;
  warnings: Array<string>;
  consumed: Budget;
  stop_reason: string | null;
  basis: Basis | null;
  issues?: Array<Issue>;
}

export interface DefinitionRef {
  key: "original" | "full" | "section" | "unit_digest" | "topic" | "domain";
  version: string;
}

export interface FieldRule {
  section_name: string;
  selectors: Array<string>;
  required: boolean;
  relations: Array<"contains" | "precedes" | "depends_on" | "supports" | "contradicts" | "supersedes" | "similar_structure" | "member_of" | "references" | "input" | "same_entity" | "mentions">;
}

export interface RepresentationDefinition {
  ref: DefinitionRef;
  title: string;
  purpose_description: string;
  rules: Array<FieldRule>;
  output_sections: Array<string>;
  generation: "never" | "draft_only";
}

export interface Realization {
  definition: DefinitionRef;
  refs: Array<FixedRef>;
  state: "direct" | "assemblable" | "needs_generation" | "stale" | "unsupported";
  missing_selectors: Array<string>;
  generator_version: string | null;
}

export interface AssociationOptions {
  mode: "off" | "existing_only" | "explore_structural";
  strategy: string;
  strategy_version: string;
  max_items: number;
  output_share: number;
  supplement_scope: Scope | null;
}

export interface QueryRequest {
  definition: DefinitionRef;
  question: string;
  keywords: Array<string>;
  scope: Scope;
  scope_ceiling: Scope;
  purpose: "exploration" | "formal" | "audit";
  association: AssociationOptions;
  budget: Budget;
  freshness: "fixed" | "current" | "allow_stale";
  result_limit: number;
  missing_policy: "reject" | "skip" | "fallback";
  fallback_definitions: Array<DefinitionRef>;
  applicability: string;
  channels?: Array<"identity" | "lexical" | "dense" | "sparse" | "graph">;
  dialect?: "plain" | "phrase" | "boolean";
  ranking_strategy?: string;
  ranking_version?: string;
  allow_index_repair?: boolean;
  max_staleness_seconds?: number | null;
  content_source?: "overview_experience" | "process" | "technical" | "all" | null;
}

export interface ContentExpandRequest {
  query_id: string;
  candidate_ids: Array<string>;
  target: "process" | "technical";
  expected_request_digest: string;
  include_packet?: boolean;
}

export interface FullDocumentsRequest {
  query_id: string;
  candidate_ids: Array<string>;
  expected_request_digest: string;
  document_type?: "research_process" | "research_report";
}

export interface ChannelHit {
  channel: string;
  provider: string;
  provider_version: string;
  rank: number;
  raw_score: number | null;
  score_meaning: string;
  representation_refs: Array<FixedRef>;
  matched_text?: string | null;
}

export interface Candidate {
  candidate_id: string;
  refs: Array<FixedRef>;
  title: string;
  excerpt: string;
  channels: Array<string>;
  score: number;
  realization: Realization;
  evidence_status: string;
  group: "direct" | "required_context" | "association";
  hits?: Array<ChannelHit>;
  evaluated_claim_refs?: Array<FixedRef>;
  unresolved_claim_refs?: Array<FixedRef>;
  unknown_facets?: Array<string>;
  content_kind?: string | null;
  knowledge_type?: "observation" | "conclusion" | "hypothesis" | "recommendation" | null;
  is_latest?: boolean | null;
  owner_type?: string | null;
}

export interface SearchReceipt {
  query_id: string;
  request_digest: string;
  candidates: Array<Candidate>;
  next_cursor: string | null;
  expires_at: string;
  gaps: Array<string>;
}

export interface QueryJob {
  query_id: string;
  state: "running" | "completed" | "cancelled" | "failed";
}

export interface AssembleRequest {
  query_id: string;
  candidate_ids: Array<string>;
  expected_request_digest: string;
}

export interface PacketFigure {
  index: number;
  caption: string;
  ref: FixedRef;
  data_url: string;
}

export interface AssemblyPart {
  group: "direct" | "required_context" | "association" | "gaps";
  heading: string;
  markdown: string;
  refs: Array<FixedRef>;
  selectors: Array<string>;
  omitted: Array<string>;
  figures?: Array<PacketFigure>;
}

export interface DocumentMatch {
  ref: FixedRef;
  title: string;
  candidate_ids: Array<string>;
  complete: boolean;
  part_indices?: Array<number>;
}

export interface MaterialPacket {
  packet_id: string;
  query_id: string;
  definition: DefinitionRef;
  parts: Array<AssemblyPart>;
  contributors: Array<FixedRef>;
  complete: boolean;
  canonical: boolean;
  documents?: Array<DocumentMatch>;
}

export interface StructuralProfile {
  refs: Array<FixedRef>;
  problem: string;
  variable_roles: Array<string>;
  mechanism: string;
  constraints: Array<string>;
  intervention: string;
  outcome_conditions: Array<string>;
  author: string;
  generator_version: string;
}

export interface AssociationProposal {
  proposal_id: string;
  source: Array<FixedRef>;
  target: Array<FixedRef>;
  common_structure: string;
  differences: Array<string>;
  transfer_conditions: Array<string>;
  verification_hint: string;
  method: string;
  state: "temporary" | "accepted_navigation" | "rejected" | "stale";
}

export interface AssociationRequest {
  query_id: string;
  seed_candidate_ids: Array<string>;
  profile: StructuralProfile | null;
}

export interface GraphEdge {
  edge_id: string;
  source: FixedRef;
  target: FixedRef;
  kind: "contains" | "precedes" | "depends_on" | "supports" | "contradicts" | "supersedes" | "similar_structure" | "member_of" | "references" | "input" | "same_entity" | "mentions";
  evidence: Array<FixedRef>;
  state: "proposed" | "accepted_navigation" | "verified_claim" | "stale" | "retracted";
  conditions: Array<string>;
  differences: Array<string>;
  proposer: string;
  generator_version: string;
  evidence_relations?: Array<"contains" | "precedes" | "depends_on" | "supports" | "contradicts" | "supersedes" | "similar_structure" | "member_of" | "references" | "input" | "same_entity" | "mentions">;
  legacy_relation?: string | null;
}

export interface DeepenRequest {
  query_id: string;
  candidate_ids: Array<string>;
  mode: "source_mapping" | "bounded_graph" | "structural_discovery";
  relation_kinds: Array<"contains" | "precedes" | "depends_on" | "supports" | "contradicts" | "supersedes" | "similar_structure" | "member_of" | "references" | "input" | "same_entity" | "mentions">;
  direction: "forward" | "reverse" | "both";
  strategy: string;
  strategy_version: string;
  cursor: string | null;
}

export interface DeepenReceipt {
  candidates: Array<Candidate>;
  edges: Array<GraphEdge>;
  proposals: Array<AssociationProposal>;
  next_cursor: string | null;
  gaps: Array<string>;
  packet?: MaterialPacket | null;
}

export interface MaintenanceRequest {
  changed_refs: Array<FixedRef>;
  scope: Scope;
  strategy: string;
  strategy_version: string;
}

export interface MaintenanceItem {
  ref: FixedRef;
  action: "retain" | "revise" | "resynthesize" | "retract" | "defer";
  reasons: Array<string>;
  affected_refs: Array<FixedRef>;
  draft_json: string | null;
}

export interface MaintenancePlan {
  plan_id: string;
  plan_digest: string;
  basis: Basis;
  items: Array<MaintenanceItem>;
  reviewed_refs: Array<FixedRef>;
  unchecked_regions: Array<string>;
  semantic_reviewer: string | null;
  context_items?: Array<AssemblyPart>;
  read_receipt?: string | null;
  review_note?: string;
  reviewer_kind?: "human" | "ai" | null;
}

export interface MaintenanceReceipt {
  commits: Array<[string, string]>;
  pending_items: Array<string>;
  index_status: "indexed" | "pending" | "failed";
  recovery_receipt: string | null;
}

export interface MaintenanceStatusRequest {
  query_id: string;
  plan_id: string;
}

export interface MaintenanceVersionStatus {
  plan_digest: string;
  parent_digest: string | null;
  reviewed: boolean;
  leaf: boolean;
  item_count: number;
}

export interface MaintenanceCommittedChange {
  ref: FixedRef;
  content_hash: string;
  client_key: string | null;
  status: "created" | "updated" | "no_change";
}

export interface MaintenanceCommitStatus {
  request_id: string;
  owner_id: string;
  commit_id: string;
  generation: number;
  save_status: "committed" | "no_change";
  changes: Array<MaintenanceCommittedChange>;
  receipt_sha256: string;
}

export interface MaintenanceReviewStatus {
  ref: FixedRef;
  review_state: "not-assessed" | "not-reviewed" | "accepted" | "disputed" | "retracted" | "superseded";
  validity: "valid" | "invalid" | "unknown";
  reasons: Array<string>;
}

export interface MaintenanceIndexStatus {
  owner_id: string;
  head: string | null;
  target_generation: number;
  indexed_generation: number | null;
  vector_generation: number | null;
  fts_status: "indexed" | "pending" | "failed";
  vector_status: "indexed" | "pending" | "failed" | "disabled";
  coverage: "complete" | "partial";
}

export interface MaintenanceAttemptStatus {
  request_id: string;
  plan_digest: string;
  state: "started" | "partial" | "committed" | "no_changes";
  completed_owner_ids: Array<string>;
  pending_owner_ids: Array<string>;
  local_receipt_owner_ids: Array<string>;
  local_completed: boolean;
  recovery_receipt: string;
}

export interface MaintenanceStatusReceipt {
  plan_id: string;
  plan_versions: Array<MaintenanceVersionStatus>;
  commits: Array<MaintenanceCommitStatus>;
  pending_owner_ids: Array<string>;
  pending_items: Array<string>;
  review_states: Array<MaintenanceReviewStatus>;
  pending_reviews: Array<FixedRef>;
  index_states: Array<MaintenanceIndexStatus>;
  attempts: Array<MaintenanceAttemptStatus>;
  resume_cursor: string | null;
  basis_stale: boolean;
}

export interface TreeRequest {
  scope: Scope;
  parent_ref: FixedRef | null;
  cursor: string | null;
  limit: number;
  view: "logical" | "storage";
  parent_node_id?: string | null;
  owner_query?: string;
}

export interface TreeNode {
  ref: FixedRef | null;
  node_id: string;
  parent_id: string | null;
  title: string;
  kind: string;
  layer: string | null;
  has_children: boolean;
  storage_role: "canonical" | "source_reference" | "projection" | "temporary";
  registered_path: string | null;
  owner_type?: string | null;
}

export interface TreePage {
  nodes: Array<TreeNode>;
  next_cursor: string | null;
}
