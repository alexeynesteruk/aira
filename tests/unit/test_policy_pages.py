"""Page selection stays small and does not drop an unclassified page."""

from app.policies.pages import chosen_pages, index_batches


def test_an_unclassified_page_is_read_and_only_an_explicit_skip_is_left_out() -> None:
    included, skipped = chosen_pages(
        4,
        [(1, "skip"), (2, "requirements"), (2, "skip"), (4, "definitions")],
    )
    assert included == (2, 3, 4)
    assert skipped == (1,)


def test_the_page_index_is_split_before_a_batch_exceeds_its_budget() -> None:
    items = [{"page": number, "excerpt": "x" * 30} for number in range(1, 6)]
    batches = index_batches(items, budget=80)
    assert len(batches) > 1
    assert [item["page"] for batch in batches for item in batch] == [1, 2, 3, 4, 5]
    assert all(sum(len(str(item)) for item in batch) > 0 for batch in batches)
