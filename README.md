# meridian-kraken

Kraken's public market data in an Open Meridian deployment's lake: a data plugin
plugin. It records each pair's daily close and bar, its last trade price and
best bid and offer, and from contract v19 every trade and the best bid and
offer with their sizes, streamed from Kraken's v2 WebSocket, for the
instruments a deployment's readers ask about, every figure exactly as Kraken
stated it and every code converted at the edge; and it keeps the order
book's depth from that WebSocket as raw records, until the lake has a kind
for it. No key: Kraken's market data is public.

It is one of the lake's crypto pair, with
[meridian-coinbase](https://github.com/open-meridian/plugin-coinbase): each runs the SDK's
data suite and its checks for a pairs venue unchanged against its own conversion
(meridian-design `plans/the-lake-prices-the-book.md`, rows 6 and 19); what the two do alike is
the SDK's (`meridian.roles.data.pairs`, open-meridian 0.31.0), never copied
between them.

**Status.** 0.8.0, built on open-meridian 0.31.0 (contract v26: the data suite's v26 cases; the book's depth kept raw, open question 232; its work the SDK's role helpers), holding the
role `data`. Not
released, uploaded or launched anywhere.

## What it does

Three datasets, declared from code in its catalogue (`declaration.py`):

| Dataset | Data | Modes | Day | Kraken's standard terms |
|---|---|---|---|---|
| `<instance>:daily` | a close and a bar per pair per day, with its volume-weighted price and trade count; 720 days back | pull, push | `Etc/UTC`, ending at 00:00 | kept, one person's |
| `<instance>:live` | the last trade's price and the best bid and offer, as prices; the best bid and offer with their sizes, as a quote | pull, stream | `Etc/UTC`, ending at 00:00 | kept two days, one person's |
| `<instance>:trades` | every trade | pull, stream | `Etc/UTC`, ending at 00:00 | kept two days, one person's |

- **What the lake wants, recorded.** A reader reads a price nothing has
  recorded; the lake asks this plugin (a want), which records it against the
  want or declines each subject with why: `not_covered` (no pair's base is
  it), `beyond_history` (older than the 720 days Kraken's `OHLC` gives),
  `source_silent` (Kraken has nothing for it). A
  standing want keeps its subjects current until the lake withdraws it: the
  live dataset at most once a second per subject and kind, the daily
  dataset's forming day every five minutes.
- **The daily close** is the last price of the UTC day: Kraken has no
  official close, so the catalogue declares the day (`day_time_zone`
  `Etc/UTC`, `day_end_minute` 0) and a daily candle gives kind `close` for
  its business date, a plain date. The day still forming is recorded valid
  until its end, with no published time, and restated under the same row key
  as it fills; a completed day carries its published time, the candle's
  end. Bars carry Kraken's volume-weighted price and trade count, and a day
  that traded nothing (count 0) carries no volume-weighted price, whatever
  Kraken writes in its place.
- **Every subject is the deployment's own record.** The lake asks for
  instruments by the deployment's ID, most of them a custodian's records
  that Kraken never resolved. The plugin reads each record (W3.6, a data plugin's
  read from contract v18 as ruled 2026-10-10) and names Kraken's asset it is
  by its identifiers: Kraken's code (`symbol` at `kraken`), else the global
  identifier Kraken's asset carries (a fiat code's ISO 4217, a native coin's
  CAIP-19), else another source's symbol that is Kraken's code (never for
  a record that is a security, by its class or a CUSIP or ISIN). Where the
  record lacks Kraken's identifiers they are reported beside the one it
  matched, so the record carries them; where that meets another record it is
  reported, and the subject is served all the same. A record naming none of
  Kraken's assets is declined, not covered: a custodian's `BTC` alone is not
  Kraken's `XXBT`, so bitcoin is named by its CAIP-19. Nothing is resolved
  for an asset no subject is: no record is minted for each asset Kraken
  lists.
- **The pair map**, kept in the plugin's storage (`meridian.roles.data.pairs.ProductMap`): a pair
  names a market, not an asset, so its base asset is a row's subject and its
  quote asset what the price is in. Kraken names assets by its own legacy
  codes (`XXBT` for bitcoin, `ZUSD` for the dollar). Which asset each
  subject is is kept there, and each quote asset of a subject's pairs is
  resolved through the deployment's instrument store, with its code as a
  `symbol` whose source is `kraken`, a record minted only where none
  resolves:
  - a fiat code Kraken documents (`ZUSD`, `ZEUR`, `ZGBP`, `ZCAD`, `ZJPY`,
    `ZAUD`, `CHF`) by its ISO 4217 code -- a `Z` is no sign of a currency;
  - a native coin (`XXBT`, `XETH`) by its SLIP-44 CAIP-19;
  - every other token by its code alone: Kraken states no network or
    contract for any asset, so each is Kraken's own instrument, its promise
    that it converts into one of the issuer's contracts (the product owner's
    ruling of 2026-10-03), never a contract's CAIP-19.
  A quote asset that does not resolve (its identifiers meet two records) is
  reported, once, and every pair quoted in it left out.
- **Money names an instrument.** A price in a currency names it by its ISO
  4217 code, which core resolves to the currency's cash instrument. A price
  in a token -- an XBT/USDT or XBT/USDC price -- names the token's own
  instrument, exactly as stated, and never a fiat code: a USDC price is never
  a dollar price. A reader values it through a dataset's price of the
  stablecoin (Kraken's USDC/USD, recorded like any pair), never by assuming 1.
- **FX** from Kraken's fiat pairs: EUR/USD is the price of the euro's cash
  instrument in dollars, as Kraken's trades made it -- a venue's price, not a
  fixing.
- **The venue** is resolved in the platform's venue master by its code
  (`symbol` `kraken`, source `kraken`: Kraken has no MIC, curation's call at
  the venue master's seed), and each row names its `VEN-` ID. A deployment
  that does not hold it gets each row with the venue left empty and the code
  beside it as reported, and the miss reported, re-resolved at the next
  mapping.
- **Exact.** Every figure is a `Decimal` from Kraken's own text, never
  through a float; Kraken's refusals under HTTP 200 are read as refusals. A value
  with more places than the contract's Decimal holds is not rounded.
- **Trades and quotes, streamed** (contract v19). A standing want of the
  live or the trades dataset -- a reader following an instrument's latest
  quote, say -- puts the pairs of its subjects on Kraken's v2 WebSocket
  (`wss://ws.kraken.com/v2`: `trade`, `ticker` on each change of the best
  bid and offer, and `book` for depth, all public), kept open while any
  want stands. A pair is
  named there by its `wsname`, with bitcoin's `XBT` as `BTC` and `XDG` as
  `DOGE`, and its figures are JSON numbers, read from their own text. Every
  trade is recorded in `trades`, never conflated, and each pair's best bid
  and offer, with their sizes, in `live` at most once a second; only for
  subjects under a standing want, in batches of at most 500. A crypto trade
  has no condition codes: it is regular, eligible to set every statistic of
  a bar in its venue's view and the consolidated one. Kraken names **the
  side that took liquidity**, recorded as the aggressor as sent; the taker's
  order type stays in the raw record. Keyed by its pair and Kraken's trade
  ID (`XXBTZUSD:t:110938306`), valid from its time, with no business date; a
  quote by its pair and instant, a side with no order left unset, never
  zero.
- **Depth, kept raw** (open question 232, ruled 2026-10-17). No lake kind
  holds the book's levels yet, so the pairs on the stream are subscribed to
  `book` as well, at Kraken's default of 10 levels a side (`convert.DEPTH`),
  in a subscription of its own: a `snapshot`, then every `update` (each
  level's new `qty`, 0 a level gone), each with its `checksum`, the CRC32 of
  the top ten levels. Each message is kept whole as a raw record and read
  into no row: the snapshot and its updates rebuild the book at any moment,
  checked by the checksum, so they are converted, losing nothing, once the
  market-data intent places a depth kind. An admin sizes the raw responses'
  window for it.
- **Kept open, with no gap.** A stream that drops, or says nothing for 30
  seconds, is opened again after a wait doubling from one second to a
  minute, inside Kraken's 150 reconnects in ten minutes per IP; each time it
  opens, the trades since the last one recorded are read back from `Trades`
  (ten pages of 1,000 at most) and recorded, so the lake has no hole and a
  reader catches up from it by the watermark it last saw. A trade heard
  twice -- the subscription's snapshot of the last 50, or the history
  overlapping the stream -- is sent once. A want for a range of trades, or
  for a quote now, is answered from REST.
- **A restart's gap, read back** (contract v20). A plugin holds nothing it
  cannot lose, so a restart leaves a gap in the trades it streams. Started
  again, it hears each standing want again and, before a subject goes back
  on the stream, reads from the lake the last trade it recorded of it
  (`ListTrades` with `latest_recorded`) and records the trades Kraken's
  history states after it (`meridian.roles.data.backfill_restart`), once per
  subject; a trade recorded again is answered unchanged by its row key.
- **Its licences** (contract v20): it reads which of its own datasets a
  deployment admin has licensed, on start and each minute, so its Datasets
  page says so exactly.

### What it cannot serve

- **More than 720 days back.** Kraken's `OHLC` gives the 720 most recent
  days; an older day is declined as beyond its history.
- **The venue in its catalogue.** The catalogue is declared from code, and
  the venue master's ID for Kraken is minted by the platform, so
  `DatasetDeclaration.venue_id` is empty; each row names the venue by the ID
  it resolves at run time.
- **A required figure that does not read** (a close past the contract's
  Decimal): the row is left unrecorded and counted on the Datasets page, its
  raw record kept. The SDK's `Price` carries no price left not known.
- **What the suite asks and Kraken never states.** Of the SDK's data
  suite's 35 cases (contract v26), eleven are not presented, each named with
  why in `tests/venue_cases.py`, as the suite allows of a case about a kind
  of data (`about`) or a field its source never states (`about_field`,
  contract v20): `the-makers-side-inverted` (Kraken names the side that
  took liquidity, never the resting order's; Coinbase presents it),
  `a-condition-converted` and `a-condition-not-converted` (Kraken states no
  condition codes: a crypto trade is regular), and `a-trade-withdrawn`
  (Kraken's feed never withdraws a trade it has stated), and contract v22's
  `reads-a-calendar` and `asks-for-a-settlement-date` (a venue trading
  24/7: it reads no settlement calendar and never computes a settlement
  date), and contract v23's three outcome cases and v26's two event-group
  cases (Kraken lists no event contract). The other 24 pass unchanged,
  `the-takers-side-stated` among them, three answered by the SDK.

## Kraken's terms

A summary, not legal advice; read the terms themselves before relying on
them. Kraken asks its prior permission (marketdata@kraken.com) for "any
non-personal commercial use of data from publicly accessible endpoints".
Without it, a deployment keeps Kraken's data for one person's own use. The
catalogue's standard terms say so (kept, one person's), and a deployment
admin confirms or replaces them in the deployment's licence on the Data
sources page, which warns where more than one person reads a plugin entitled
to it. Nothing here says that a deployment meets Kraken's terms.

So **no real Kraken response is committed** to this public repository: the
tests and sample data use synthetic exchanges (`src/kraken/synthetic/`),
shaped exactly as Kraken documents and sends its answers, with invented
values and an invented token. A developer's recordings of Kraken's real
answers stay outside the repository and are replayed locally
(`make e2e-recorded`).

## Settings

| Setting | What it does |
|---|---|
| Sample data (`sample_data`) | A developer's setting, shown only on a development deployment: answer from the synthetic exchanges this plugin carries instead of calling Kraken, or from a developer's recorded exchanges where its storage holds them (`recorded/`). |
| Raw responses' window (`responses_window_days`, `responses_past_window`) | The SDK's, for the plugin's one kind of raw record: how long Kraken's answers stay in its storage (30 days by default), and whether a day past it is archived, kept or deleted. |

No secret: Kraken's public market data needs no key.

## Its pages, under Manage

The data role's two pages (meridian-design
`spec/plugin-pages-follow-their-role.md`), the same sections, rows, labels
and "not set up yet" states as every data plugin's, drawn from the SDK's
role templates (`meridian.roles.data`); Kraken's nuance only at their
extension points. A data plugin shows no market data: viewing prices is for
the reading roles.

- **Connection**: "Key" -- the mode (Live, or Sample data), "No key needed",
  what Kraken entitles it to (public data: every pair it lists) and, the
  role's row for a source of one venue, the venue master's ID it resolved;
  "Limits and use" -- what Kraken allows and what the plugin spends of it,
  its calls and the rate-limited ones waited out, the last call and the last
  error; "Stream" -- the session: open or not, the pairs on it, its
  reconnects and messages and its last error.
- **Datasets**: "Served" -- each dataset of its catalogue, its data, how its
  rows arrive, its day, its default terms and whether a deployment admin has
  licensed it ("Licensed" or "Not licensed yet", read from the deployment
  from contract v20), what it recorded and declined and when it last
  recorded; "Wants" -- the wants it heard and the standing wants it keeps
  current, searched and paged by the kit's `om-pager`; "Subjects" -- whether
  the deployment lets it read an instrument's record; then a section under
  Kraken's name with the pair map (pairs listed, and mapped for the subjects
  the lake asked for; assets not resolved). Before the lake has asked
  anything it says the next step: "No wants yet", a deployment admin
  licensing its datasets on Data sources.

Its Summary carries the data role's figures, in the role's order:
Connection, Entitled at the vendor, Stream and Last recorded. Both pages
fit one screen at 1440x900 and 390x844, rows one line each.

### Offered to agents

Each page is a read tool on the deployment's MCP surface, answering the record
the page shows: `read_connection` and `read_datasets`, at the plugin's admin
level. The plugin has no route that changes anything.

## Raw responses

Every answer Kraken sends, an error as much as a candle, is kept in the
storage the deployment grants the plugin before anything is read from it,
with the request that asked for it, its status and freshness headers, and
when it arrived (`meridian.edge.RawStore`); a live answer is a line of its day's file, added
only when it changed, and each message of the stream a line of its day's
file for its channel (a heartbeat, which states nothing, is not kept): the
book's depth among them, `stream/book.jsonl`, the only place it is kept
until a depth kind is placed. Each row names its raw record (`RawRecordRef`) and
where in it the row came from. Kept in units of a UTC day under
`responses/`, moved past the window through the SDK.

## Proven against a released runtime

    make e2e

runs the plugin with sample data on core's plugin harness, the runtime and
harness of the core it pins by digest, beside the e2e's reader
(`e2e/reader.py`, a `reporting` plugin run from the plugin's image, holding
`custody` to resolve a custodian's records and `signal` to read trades and
quotes): the catalogue listed, the listing read with no record minted for
any asset, the three datasets licensed and the reader entitled, a custodian's bitcoin (by its CAIP-19 and symbol) read
and named, and a day's closes wanted and recorded against the want (XXBTZUSD's in
dollars, XBTUSDC's on USDC's own instrument, exactly), the dollar declined
and the euro's rate in dollars recorded, bitcoin's live prices kept current
until withdrawn, bitcoin's pairs streamed -- the synthetic venue dropping the
first connection, the plugin opening it again and reading back the trades it
missed -- every trade recorded once with its aggressor, read over the day and
after the reader's watermark and heard, and each pair's latest quote with
its sizes, the book's depth kept raw, both read tools answering what the pages show, and `store lake`
numbering each dataset's rows with no holes (`e2e/run.py` says each step).

    make e2e-recorded RECORDED=<dir> DAY=<a day it holds>

runs the same replaying a developer's recorded exchanges, reading the day
named and holding each row to its shape rather than to the synthetic values:
a directory of this plugin's raw records of Kraken's real answers, REST and
the stream's messages, recorded under personal use, never committed.

## Working on it

    make ci-local        # every gate: lint, tests, plugin check, the image, e2e, the pair the same
    make test            # the tests, the SDK's data suite among them
    make preview         # preview/: each page on synthetic data, linking the kit
    make install-hooks   # git push runs ci-local first

`AGENTS.md` is for any coding agent working on it; `CLAUDE.md` leads Claude
Code there. The documentation for a deployment admin is in `docs/`.

## Licence

Apache-2.0. See `LICENSE` and `NOTICE`. Kraken is a trademark of its owner;
this project is not affiliated with or endorsed by Kraken.
