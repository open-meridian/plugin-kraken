# Changelog

## 0.10.0

On open-meridian 0.33.1, contract v28 (plugin-common-v28), on core v28's
harness.

- **The feed delay, reported** (ruling 518, required again from contract
  v28): `__main__` gives the SDK's `pairs.Feed` a `roles.Latency`, so each
  row streamed or kept current has its age at the edge recorded, reported
  every 10 seconds (`ReportLatency`); `reports-its-feed-delay` is presented
  by the SDK's producer on the streamed ticker.
- **A crossed quote recorded invalid** (ruling 424):
  `a-crossed-quote-is-recorded-invalid` is presented on a ticker whose best
  bid is above its best offer (`venue_cases.CROSSED_TICKER`), judged by the
  SDK's edge checks.
- **Not presented** (ruling 602): the option-chain, filings, holdings,
  dividend and rating cases (the SDK's `PAIRS_NOT_PRESENTED`), and
  `a-duplicate-is-recorded-suspicious` and `rows-after-a-gap-are-suspicious`:
  Kraken's v2 ticker numbers no message.
- **`meridian plugin migrate`** (to_0_33_0, to_0_33_1): e2e/reader.py's
  SubjectRefs are `meridian.SubjectRef` (ruling 599).
- **The pins:** open-meridian 0.33.1 and plugin-python:0.33.1 by tag and
  digest; core v28's runtime and harness at `8def82a` (chart 0.1.313) by
  digest; `meridian` stays 0.1.52 in check.yaml.
- The README's "Not released" line is gone.

## 0.9.0

On open-meridian 0.32.2, contract v27 (the v27 plan's §C, liveness; and §G:
v27 pins, `plugin check` clean, docs).

- **The stream's liveness** (ruling 418). Kraken sends only on a change; its
  v2 `heartbeat`, about once a second when nothing else is sent, and every other message, is the stream's sign of life. The SDK's
  `pairs.Feed` records it once a pass as the `live` dataset's liveness
  (`Wants.liveness`, `RecordLiveness`), confirming every quote in force,
  never as a row. `records-a-datasets-liveness` is presented on a
  heartbeat alone, as the case states it (`venue_cases.HEARTBEAT`), and a
  test holds that the heartbeat records the liveness once and no row.
- **No declared delay.** Kraken's public feed is real time, so no dataset sets
  `declared_delay_ns`; each row's age at the edge is not recorded.
- **The data suite's v27 cases.** Of 44, nineteen are not presented, each with
  why: the seven rates cases (a pairs venue publishes no rates) and
  `reports-its-feed-delay` ("core receives ReportLatency from contract v28,
  ruling 515", ruling 518) from the SDK's `PAIRS_NOT_PRESENTED`, beside this
  venue's own; `queries-the-lake-within-bounds`, now about trades, keeps
  the SDK's producer. The other 25 pass, three answered by the SDK.
- **The licence's new fields are not set.** SDK 0.32.2's `DatasetLicence`
  attribution fields are left unset: core v27 registers a catalogue
  without them, so setting them would be refused. The terms text, the
  Datasets page and `docs/terms.md` are unchanged.
- **The e2e** (step 7): the reader hears the `live` dataset's liveness and
  reads it on the lake's dataset listing, beside no declared delay.
- **The pins**: open-meridian 0.32.2, as released on PyPI, and
  plugin-python:0.32.2 by tag and digest (`sha256:2235d96d...020b80`) in the
  Dockerfile; core v27's runtime and harness (a5da59a, merged as 6d346b3,
  chart 0.1.310) by digest; `meridian` 0.1.52 in check.yaml, carrying
  contract v27's suites.

## 0.8.0

On open-meridian 0.31.0, contract v26 (the v26 plan's §8: "Coinbase and
Kraken: trade recording to the lake. Depth per open question 232").

- **Trades to the lake, as they were.** Every trade of a streamed pair goes
  to `trades` through the SDK's data-role helpers
  (`meridian.roles.data.pairs.Feed`, `plugin.record_trades`), the best bid
  and offer to `live`; the catalogue is unchanged. Who reads them is the
  deployment's grants: trades and quotes for `signal` and `ems`, conflated
  prices and bars for `reporting`. 0.31.0's new helpers (listings, custody
  pages, the Trader's charges, event groups, pricing) replace nothing here.
- **Depth, kept raw** (open question 232, ruled 2026-10-17). The stream's
  pairs are subscribed to Kraken's v2 `book` channel too, at its default of
  10 levels a side (`convert.DEPTH`), in a subscription of its own; each
  `snapshot` and `update` is kept whole as a raw record under `responses/`
  (`stream/book.jsonl`) and read into no row, since no lake kind holds
  depth: it is converted once the market-data intent places one. The
  Connection page's stream endpoint says so. Size `responses_window_days`
  with it in mind.
- **The data suite's v26 cases.** `queries-the-lake-within-bounds` passes
  on the SDK's producer; `reports-an-event-group` and
  `reports-a-flag-the-venue-does-not-state` are not presented, with why
  (Kraken lists no event contract).
- **Tests**: the depth subscription, the depth kept whole and read into
  nothing, on synthetic exchanges (a snapshot and an update, and the
  reconnected stream's new snapshot), each synthetic checksum Kraken's own
  over the book it leaves; the e2e's step 9 finds the depth in storage.
- **The pins**: open-meridian 0.31.0, as released on PyPI, and
  plugin-python:0.31.0 by tag and digest (`sha256:e041f83c...f5d2`) in the
  Dockerfile; core v26's runtime and harness (17a13a2, merged as 648e25f,
  chart 0.1.308) by digest; `meridian` 0.1.49 in check.yaml, the first
  to carry contract v26's suites.

## 0.7.0 (2026-10-19)

On open-meridian 0.30.0, contract 25 unchanged: the data role's work is
the SDK's (sdk-contract/the-sdk-carries-each-roles-common-logic; ruling
202).

- **The data role from the SDK's helpers.** `market.py`, `dgm.py`,
  `products.py` and `raw.py`, kept byte for byte with plugin-coinbase, are
  gone: the work is `meridian.roles.data.pairs.Feed` over this venue's
  values and `ProductMap`, raw records `meridian.edge.RawStore`, and the
  pages the SDK's for a pairs venue (`page.py` builds them; `templates/`
  gone), answering the kind's `ConnectionRead` and `DatasetsRead`.
  `stream.py` stays: this plugin's own transport, handed to the feed as its
  stream factory.
- **suite-same retired.** The copied tests (`test_suite`, `test_dgm`,
  `test_page`, `test_raw`, `conftest`) are one class,
  `tests/test_data_role.py`, running the SDK's `PairsChecks` against this
  plugin's conversion and the data suite by name; raw records are tested in
  the SDK. The Makefile's `suite-same`, `PAIR` and `SAME` are gone.
- **The pins**: open-meridian 0.30.0, as released on PyPI, and
  plugin-python:0.30.0 by tag and digest
  (`sha256:a238c6d9...3473ed6`) in the Dockerfile, which `make image` now
  builds on as an upload does; core v25's runtime and harness (abf028f) and
  `meridian` 0.1.46 as 0.6.0 set them.

Earlier versions are described in the git history.