"""Read authored facets through the existing canonical record and source ACL.

Filters are AND across dimensions and OR within one dimension. Empty requested
sets never become unrestricted. Explicit unknown inclusion affects only absent
classifications, never a known failure, low confidence, or withdrawn review.
"""
from memory.contracts import canonical_hash


def matches(expected, actual, include_unknown=False):
    """Match exact labels; absence is unknown, rather than successful/certain."""
    if expected is None:
        return True
    if not expected:
        return False
    values = set(actual) or {"unknown"}
    return bool(set(expected) & values or include_unknown and "unknown" in values)


def authored(record):
    """Project only explicit facets or unambiguous legacy structured fields.

The optional canonical object is authoritative when present. An empty attempts
array says no attempt classification is available; it does not invite a second
classifier to reinterpret the surrounding prose or legacy observation labels.
"""
    payload = record.get("payload", {})
    facets = payload.get("knowledge_facets")
    if facets is not None:
        return {"roles": tuple(facets["roles"]),
                "outcomes": tuple(attempt["outcome"] for attempt in facets["attempts"]),
                "confidence": facets["confidence"], "applicability": facets["applicability"]}
    roles = ()
    if record.get("kind") == "experience":
        roles = ("experience",)
    elif record.get("kind") == "detail" and payload.get("unit_type") == "method":
        roles = ("method",)
    # A structured failure record is an actual unsuccessful attempt. A list of
    # possible failure_modes, a Run's execution success, or the word "success"
    # in observation does not establish a scientific attempt outcome.
    outcomes = ("failure",) if record.get("kind") in {"event", "narrative"} and payload.get("failure") else ()
    applicability = None
    if record.get("kind") == "experience":
        applicability = {"conditions": payload.get("applicable", []), "exclusions": payload.get("prohibited", [])}
    elif record.get("kind") == "detail" and payload.get("retrieval_description"):
        description = payload["retrieval_description"]
        applicability = {"conditions": description["applicable"], "exclusions": description["not_applicable"]}
    return {"roles": roles, "outcomes": outcomes, "confidence": (), "applicability": applicability}


def applicability_matches(scope, applicability):
    """Match the currently exposed condition arrays without substring inference.

Requested conditions must be explicitly present and not prohibited. Request
exclusions remove records asserting those conditions. Description text is not a
classification field. The full legacy Applicability DTO (including requested
subject versions and dates) is not silently accepted through these arrays.
"""
    required, excluded = set(scope.applicability_conditions), set(scope.applicability_exclusions)
    if not required and not excluded:
        return True
    if applicability is None:
        return bool(scope.include_unknown)
    conditions = set(applicability["conditions"])
    prohibited = set(applicability["exclusions"])
    return required <= conditions and not required & prohibited and not excluded & conditions


def confidence_levels(record, scope, claim_refs=None):
    """Use assessments of this fixed target, never an unrelated/other claim.

Record candidates may match one of their own current claims. An exact claim
candidate supplies only that claim's (ID, SHA) pair. Merely citing a high
confidence source must not give the citing record high confidence.
"""
    own_claims = {(claim["claim_id"], canonical_hash(claim)) for claim in record.get("payload", {}).get("claims", [])}
    selected = own_claims if claim_refs is None else set(claim_refs) & own_claims
    values = []
    for assessment in authored(record)["confidence"]:
        target = assessment["target"]
        claim_matches = target["target_kind"] == "claim" and (target["target_id"], target["sha256"]) in selected
        record_matches = claim_refs is None and target["target_kind"] == "record" and (
            target["target_id"], target["revision"], target["sha256"]) == (
                record.get("record_id"), record.get("revision"), record.get("record_hash"))
        if (claim_matches or record_matches) and applicability_matches(scope, assessment["applicability"]):
            values.append(assessment["level"])
    return values or ["unknown"]


def record_matches(record, scope, evidence=None):
    facets = authored(record)
    targets = evidence.get("assessed_claims") if evidence is not None else None
    # An empty assessed set on a record with claims means the per-claim AND
    # filter rejected them. Recasting that rejected set as absent confidence
    # would let include_unknown re-admit a known low-confidence sibling.
    if scope.confidence_levels is not None and targets == [] and record.get("payload", {}).get("claims"):
        return False
    return (matches(scope.roles, facets["roles"], scope.include_unknown)
            and matches(scope.outcomes, facets["outcomes"], scope.include_unknown)
            and matches(scope.confidence_levels, confidence_levels(record, scope, targets), scope.include_unknown)
            and applicability_matches(scope, facets["applicability"]))


def unknown_facets(record, scopes, claim_refs=None):
    """Name only dimensions whose requested match depends on unknown inclusion.

No target identity, owner count, source title or path enters this diagnostic.
The same fixed confidence-target selection is used for filtering and disclosure,
so a sibling's known assessment cannot hide an exact claim's missing assessment.
"""
    projected = authored(record)
    missing = set()
    for scope in scopes:
        dimensions = (("roles", scope.roles, projected["roles"]),
                      ("outcomes", scope.outcomes, projected["outcomes"]),
                      ("confidence", scope.confidence_levels, confidence_levels(record, scope, claim_refs)))
        for name, expected, actual in dimensions:
            values = set(actual) or {"unknown"}
            if (expected and "unknown" in values and (scope.include_unknown or "unknown" in expected)
                    and not (set(expected) - {"unknown"}) & values):
                missing.add(name)
    return sorted(missing)
