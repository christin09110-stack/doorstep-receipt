"""Two table defects that a screenshot found and a unit test can hold.

1. The BASIS cell printed `RECORD` / `ED` and `classi` / `ficati` / `on`.
   `_shell.html` set the right default on one line and took it straight back
   on the next, for the one element that was breaking, under a comment that
   claimed the bug was already fixed.

2. The claim file's table was 64px wider than the cream sheet it sits on, with
   two rows on it, so the YOUR NOTE column and every row rule ran off the paper
   onto the tan background — and the filed date printed as `2026-` / `09-23`.

The geometry itself was measured in a browser (0px overflow at 1280 and at
390). What is asserted here is the CSS and markup that produce it, because that
is what a later edit would undo.
"""

import datetime as dt
from pathlib import Path

from doorstep_receipt import views
from doorstep_receipt.carrier import ManualEntryAdapter
from doorstep_receipt.reconcile import reconcile
from doorstep_receipt.records import ClaimRecord

SHELL = (Path(__file__).resolve().parent.parent / "templates" / "_shell.html").read_text()


def _rule(selector_fragment: str) -> str:
    """The one declaration block whose selector contains this fragment."""
    for line in SHELL.splitlines():
        stripped = line.strip()
        if stripped.startswith(selector_fragment) and "{" in stripped:
            return stripped
    raise AssertionError(f"no rule found for {selector_fragment!r}")


def test_the_basis_span_no_longer_opts_back_into_breaking_anywhere():
    anywhere = [
        line.strip()
        for line in SHELL.splitlines()
        if "overflow-wrap: anywhere" in line and line.strip().startswith("table td")
    ]

    assert anywhere, "the rule that lets a tracking number break has gone entirely"
    for line in anywhere:
        assert ".basis" not in line, line


def test_a_tracking_number_may_still_break_anywhere():
    """It is 22 digits in a narrow column and it has to break somewhere."""
    rule = _rule("table td code")

    assert "overflow-wrap: anywhere" in rule


def test_the_basis_words_wrap_between_themselves_and_never_inside_one():
    block = SHELL[SHELL.index("table td .basis {"):]
    block = block[: block.index("}")]

    assert "word-break: keep-all" in block
    assert "overflow-wrap: normal" in block


def _record() -> ClaimRecord:
    claim = ManualEntryAdapter().fetch_claim(
        tracking_number="9400111899223197428490",
        carrier_name="USPS",
        status="delivered",
        claimed_at=dt.datetime(2026, 9, 20, 14, 11, tzinfo=dt.timezone.utc),
    )
    return ClaimRecord(
        claim_id="abc123",
        result=reconcile(claim, []),
        created_at=dt.datetime(2026, 9, 23, 10, 0, tzinfo=dt.timezone.utc),
        device_name="Front Door",
        notes="",
    )


def test_neither_date_in_a_claim_row_is_allowed_to_break_at_a_hyphen():
    row = views._claim_row(_record())

    assert '<td class="nowrap" data-label="Filed">' in row
    assert '<td class="nowrap" data-label="Claimed">' in row


def test_the_tracking_cell_is_the_one_that_may_break_anywhere():
    row = views._claim_row(_record())

    assert '<td class="break-anywhere" data-label="Tracking">' in row


def test_the_table_is_given_a_floor_for_each_of_those_two_columns():
    """Without them the auto layout squeezes a 22-digit number onto six lines
    and a two-word carrier name onto two."""
    assert "table.log td.break-anywhere { min-width:" in SHELL
    assert 'table.log td[data-label="Carrier"] { min-width:' in SHELL


def test_the_verdict_chip_may_wrap_inside_a_table_cell():
    """`white-space: nowrap` on a four-word label set the whole table's minimum
    width, which is what pushed it off the paper."""
    rule = _rule("table td .stamp-chip")

    assert "display: inline-block" in rule
    assert "white-space: normal" in rule


def test_the_chip_still_refuses_to_wrap_everywhere_else():
    """One box in the meta grid, where there is room for it."""
    block = SHELL[SHELL.index("  .stamp-chip {"):]
    block = block[: block.index("}")]

    assert "white-space: nowrap" in block
