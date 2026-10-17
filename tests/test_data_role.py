"""The SDK's checks for a data plugin of a pairs venue, run unchanged against
this plugin's own conversion (`meridian.roles.data.testing.PairsChecks`):
the data suite, the venue's work past the suite's cases, and the pages.
tests/venue_cases.py names Kraken's synthetic exchange for each."""

from __future__ import annotations

from meridian.roles.data.testing import PairsChecks

import venue_cases


class TestPairs(PairsChecks):
    venue = venue_cases
