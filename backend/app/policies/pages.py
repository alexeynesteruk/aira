"""Choose guideline pages, then keep each page's model input small.

The rule set is not built from the whole PDF. An index call sees a short excerpt
of each page and marks it as a requirement, a definition, or something to skip.
Any page the index does not classify is read anyway. The builder then sends one
full page at a time, with the rule set validated so far.
"""

import json
from dataclasses import dataclass

from app.schemas import Policy, StageUsage

EXCERPT_CHARACTERS = 500
INDEX_BUDGET_CHARACTERS = 60_000


def page_excerpts(pages: object, *, limit: int = EXCERPT_CHARACTERS) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for page in pages:  # type: ignore[attr-defined]
        text = " ".join(block.text for block in page.blocks)
        items.append({"page": page.page, "excerpt": text[:limit]})
    return items


def index_batches(
    items: list[dict[str, object]], *, budget: int = INDEX_BUDGET_CHARACTERS
) -> list[list[dict[str, object]]]:
    """Split the page index so one selection call stays inside a character budget."""
    batches: list[list[dict[str, object]]] = []
    current: list[dict[str, object]] = []
    size = 0
    for item in items:
        encoded = len(json.dumps(item, ensure_ascii=False))
        if current and size + encoded > budget:
            batches.append(current)
            current, size = [], 0
        current.append(item)
        size += encoded
    if current:
        batches.append(current)
    return batches


def chosen_pages(
    page_count: int, roles: list[tuple[int, str]]
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Return pages to read and pages explicitly skipped.

    A page with no decision is read. Only an explicit ``skip`` is left out.
    ``requirements`` and ``definitions`` are both read, in page order.
    """
    decision: dict[int, str] = {}
    for page, use in roles:
        if 1 <= page <= page_count and page not in decision:
            decision[page] = use
    included: list[int] = []
    skipped: list[int] = []
    for page in range(1, page_count + 1):
        if decision.get(page) == "skip":
            skipped.append(page)
        else:
            included.append(page)
    return tuple(included), tuple(skipped)


def rule_snapshot(policy: Policy) -> dict[str, object]:
    """Compact tree the next page can extend without resending the guideline."""
    return {
        "title": policy.title,
        "scope_summary": policy.scope_summary,
        "root_id": policy.root_id,
        "criteria": [
            {
                "criterion_id": item.criterion_id,
                "wording": item.wording,
                "quotes": [
                    {"page": source.page, "quote": source.excerpt} for source in item.sources
                ],
            }
            for item in policy.criteria
        ],
        "nodes": [node.model_dump(mode="json", exclude={"sources"}) for node in policy.nodes],
    }


def render_index(document_id: str, batch: list[dict[str, object]]) -> str:
    return json.dumps(
        {"input_kind": "policy_page_index", "document_id": document_id, "pages": batch},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def render_page(
    document_id: str,
    page_number: int,
    blocks: list[str],
    policy: Policy | None,
) -> str:
    return json.dumps(
        {
            "input_kind": "policy_one_page",
            "document_id": document_id,
            "page": page_number,
            "blocks": blocks,
            "current_rule_set": rule_snapshot(policy) if policy is not None else None,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


@dataclass(frozen=True)
class PageSelection:
    pages: tuple[int, ...]
    skipped: tuple[int, ...]
    usage: StageUsage | None = None
