# Changelog

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