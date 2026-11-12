"""The declaration: the catalogue declared from code, as registration and
`meridian plugin upload` read it."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from kraken.declaration import DECLARATION
from kraken.declared import CATALOGUE, SAMPLE_DATA, TERMS


def test_three_datasets_daily_live_and_trades_on_the_utc_day() -> None:
    assert [d.key for d in CATALOGUE] == ["daily", "live", "trades"]
    for dataset in CATALOGUE:
        assert (dataset.vendor, dataset.day_time_zone, dataset.day_end_minute) == (
            "Kraken",
            "Etc/UTC",
            0,
        )
        assert dataset.venue_id == "", "the venue's ID is resolved at run time, never invented"
    daily, live, trades = CATALOGUE
    assert list(daily.data_types) == [
        "meridian.v1.Price",
        "meridian.v1.Bar",
        "meridian.v1.Bar.vwap",
        "meridian.v1.Bar.trade_count",
    ]
    assert daily.history == 720, "OHLC's 720 most recent days"
    assert list(live.data_types) == ["meridian.v1.Price", "meridian.v1.Quote"]
    assert list(trades.data_types) == ["meridian.v1.Trade"], "trades apart from live prices"
    # Contract 30 (ruling 1032): Kraken's terms in words, no licence -- one
    # person's without Kraken's permission for non-personal use; a gap is
    # asked again where Kraken serves history.
    assert {d.terms_and_pricing for d in CATALOGUE} == {TERMS}
    assert "one person's own use" in TERMS and len(TERMS) <= 2000
    assert [d.gap_recovery for d in CATALOGUE] == ["backfill", "stream_only", "backfill"]
    assert not any(d.sessions_calendar_id for d in CATALOGUE), "it trades around the clock"


def test_no_key_needed_and_sample_data_a_developers_setting() -> None:
    # The data role's settings (spec/plugin-pages-follow-their-role): one
    # environment and no credential, so sample data alone, labelled as the
    # SDK's helper labels it.
    assert isinstance(DECLARATION.settings, tuple)
    [setting] = DECLARATION.settings
    assert (setting.name, setting.developer, setting.secret) == (SAMPLE_DATA, True, False)
    assert (setting.label, setting.default) == ("Sample data", False)
    assert DECLARATION.storage is not None


def test_upload_reads_the_same_declaration() -> None:
    printed = subprocess.run(
        [str(Path(sys.executable).parent / "meridian-declaration"),
         "kraken.declaration:DECLARATION"],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    datasets = json.loads(printed.stdout)["catalogue"]["datasets"]
    assert [d["key"] for d in datasets] == ["daily", "live", "trades"]
    assert [d["modes"] for d in datasets] == [["pull", "push"], ["pull", "stream"],
                                              ["pull", "stream"]]  # fmt: skip
