"""The SDK's checks for a data plugin of a pairs venue, run unchanged against
this plugin's own conversion (`meridian.roles.data.testing.PairsChecks`):
the data suite, the venue's work past the suite's cases, and the pages.
tests/venue_cases.py names Kraken's synthetic exchange for each."""

from __future__ import annotations

from meridian.roles.data.testing import PairsChecks, pairs_producers
from meridian.suites import run

import venue_cases


class TestPairs(PairsChecks):
    venue = venue_cases


def test_the_data_suite_passes_unchanged() -> None:
    """The SDK's data suite, each case on this plugin's own exchange
    (`meridian.suites.run`), as `meridian plugin check` asks to see."""
    v = venue_cases
    report = run("data", pairs_producers(v), not_presented=v.NOT_PRESENTED, instance_id=v.VENUE)
    assert report.passed, report.failures
