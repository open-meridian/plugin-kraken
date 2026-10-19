# Changelog

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