# kraken

A Meridian plugin, in Python on the open-meridian SDK, that puts Kraken's
public market data into a deployment's lake, its codes converted
at the edge: a data plugin (the role `data`; W10, contracts v18 to v20). It runs beside a sidecar in a
Meridian deployment and reaches nothing else but that sidecar and Kraken's
public REST and v2 WebSocket (no key): what it may publish and subscribe to comes
from the role `pyproject.toml` declares under `[tool.meridian]` (`data`), once
a deployment admin approves it.

- `src/kraken/__main__.py` connects to the sidecar declaring the catalogue,
  the storage and the settings (`declaration.py`) and the pages (`page.py`),
  serves them, hears what the lake wants (`plugin.receive(observations_wanted=...,
  want_withdrawn=...)`) and keeps each standing want current, and keeps the
  venue's stream open while a standing want puts anything on it
  (`Feed.keep_streaming`).
- **Kraken's vocabulary is read in one place.** `venue.py` is the HTTP
  client (the standard library's: no third-party dependency), every answer
  kept as a raw record before anything is read from it (`meridian.edge.RawStore`), an answer
  good only with an empty `error` list (Kraken refuses under HTTP 200);
  `convert.py` reads Kraken's answers into the venue's values (`meridian.roles.data.pairs`'s):
  its legacy asset codes (`XXBT`, `ZUSD`) with the one global identifier its
  documentation supports, daily OHLC, the ticker, the level-1 book, trades
  and the v2 stream's messages, every
  figure a `Decimal` from Kraken's text (`json_decimal`, never `float`).
  `synthetic.py` answers instead of Kraken with sample data: the synthetic
  exchanges in `src/kraken/synthetic/`, or a developer's recorded ones.
- **What every data plugin of a pairs venue does is the SDK's**
  (open-meridian 0.33.1; nothing is copied between plugins): naming each
  subject, resolving, recording, answering wants and keeping them current,
  and reading back the stream's gaps and a restart's are
  `meridian.roles.data.pairs.Feed`, over the venue's values (`pairs.Asset`,
  `Listed`, `Candle`, `Tick`, `Top`, `Print`) and its product map
  (`pairs.ProductMap`, kept in storage); raw records are
  `meridian.edge.RawStore`; the pages are the SDK's for a pairs venue
  (`page.py` builds them with `pairs.connection_read` and `datasets_read`);
  and `tests/test_data_role.py` runs the SDK's checks
  (`meridian.roles.data.testing.PairsChecks`) against this plugin's
  conversion. What is Kraken's own is here: `convert.py`, `venue.py`,
  `stream.py` (the WebSocket, spoken with the standard library, and its
  reopening: this plugin's transport, handed to the feed as its stream
  factory), `synthetic.py`, `declared.py`, `declaration.py`, and
  `tests/venue_cases.py`, the one test module that knows which venue this is.
- **The lake's rules, which the SDK's data suite holds** (`tests/test_data_role.py`
  runs it through the SDK's checks): name every subject before
  recording -- read its record (`resolve_instrument`, W3.6) and name
  Kraken's asset by its identifiers (Kraken's code, the global identifier
  Kraken's asset carries, another source's symbol that is Kraken's code),
  joining Kraken's identifiers to the record where it lacks them; never
  resolve an asset no subject is, so no record is minted per listed asset --
  and resolve each quote asset of a subject's pairs (`pairs.ProductMap`: a
  documented fiat code by `iso4217`, a native coin by its SLIP-44 `caip19`,
  with its code as a `symbol` whose source is `kraken`; every other token is
  Kraken's own instrument, by its code alone, since Kraken states no network
  or contract for any), reporting what does not resolve
  (`report_missing_instrument`), once; resolve the venue by its
  code (`resolve_venue`, by `convert.VENUE_IDENTIFIERS`: `symbol` `kraken` at `kraken`, Kraken having no MIC), and where the deployment does not hold it leave each row's
  `venue_id` empty with the code beside it as reported. A price in a
  currency names it by its ISO 4217 code; a price in any token -- USDT,
  USDC -- names the token's own instrument (`Money(amount,
  instrument_id=...)`), never a fiat code: a stablecoin is never its
  currency. A daily close is keyed by its product and candle
  (`XXBTZUSD:1d:<start>`), its business date a `datetime.date`, so the day
  still forming is restated under the same key; a completed day carries its
  `published` time. Wants are recorded against (`want_id=`) or declined per
  subject with the reason (`not_covered`, `beyond_history`,
  `source_silent`).
- **Trades and quotes, streamed** (contract v19; the SDK carries typed
  operations only, so the stream is the plugin's). A standing want of the
  live or the trades dataset puts its subjects' products on the venue's
  stream (`Feed.restream`); `convert.py` says what to subscribe and reads each
  message, kept as a raw record first, into `pairs.Print` (a trade, with
  the venue's side and whose side it is -- its `side` is the taker's, recorded as the aggressor as sent) and `pairs.Top` (the best
  bid and offer with sizes). The data plugin records every trade in `trades`
  (`plugin.record_trades`, never conflated) and each product's latest quote
  in `live` (`plugin.record_quotes`, at most once a second), in batches of at
  most 500, only for subjects under a standing want; a crypto trade is
  regular, eligible in both views with no characteristic; keyed
  `<product>:t:<trade ID>` and `<product>:q:<ns>`, no business date; a side
  with no order unset, never zero. Each time the stream opens again, the
  trades since the last one recorded are read back from the venue's REST
  history (`Market.trades`), so a drop leaves no gap; a trade heard twice is
  sent once. A case of the SDK's suite about something the venue never
  states (condition codes, a withdrawal, the side it does not name: a case
  about a field, `about_field`, from contract v20) is named in
  `tests/venue_cases.NOT_PRESENTED` with why, never faked.
- **Liveness and latency** (contract v27; ruling 418). Every stream message,
  the venue's heartbeat among them, is the stream's sign of life: the SDK's
  `pairs.Feed` records it once a pass as the `live` dataset's liveness
  (`Wants.liveness`, `RecordLiveness`), never as a row; the suite's
  `records-a-datasets-liveness` is presented on a heartbeat alone
  (`tests/test_data_role.py`, `venue_cases.HEARTBEAT`). The feed is real
  time: declare no `declared_delay_ns`. `reports-its-feed-delay` is
  presented (ruling 518): `__main__` gives the feed's `Wants` a
  `roles.Latency` and runs its report; never hand-send `report_latency`.
- **Depth, kept raw** (open question 232, ruled 2026-10-17). No lake kind
  holds the book's levels, so the stream's pairs are also subscribed to
  `book` at `convert.DEPTH` levels a side (its own subscription, as the
  trades' and the ticker's are), and each `snapshot` and `update` is kept
  whole as a raw record and read into no row. Record no depth anywhere in
  the lake, and invent no kind or dataset for it: it is converted from
  these raw records once the market-data intent places a depth kind. The
  synthetic book's checksums are Kraken's own, computed over the book each
  message leaves (`tests/test_convert.py` holds them).
- **A data plugin shows no market data** (ruled 2026-10-03). Its pages are
  the data role's (meridian-design `spec/plugin-pages-follow-their-role.md`):
  Connection and Datasets, under Manage alone, drawn by the SDK's templates for
  a pairs venue (`meridian/roles/data/pairs/connection.html`, `datasets.html`,
  extending the role's) from `pairs.ConnectionRead` and
  `pairs.DatasetsRead`.
  Their sections, rows, labels and "not set up yet" states are the role's
  and are never renamed, reordered or dropped; the venue's nuance goes only
  at the template's blocks (`vendor_rows`, `vendor_sections`, ...): the
  venue master's ID under "Key", the stream's session under "Stream", the
  product map in a section under the venue's name. Never a price, bar or
  candle (the SDK's checks hold every page to it). Each page declares
  the record it renders (`answers=`), so each is a read tool on the
  deployment's MCP surface, `read_connection` and `read_datasets`, answering
  what the page shows under the role's field names; keep the two in step.
  Both fit one screen at 1440x900 and 390x844 (one-line rows; the wants
  searched and paged by the kit's `om-pager`). The Summary's figures are
  the role's (`page.figures_now`, `meridian.roles.data.figures`), sent on
  the heartbeat each minute.
- **A restart's gap and its licences** (contract v20). Before a subject
  goes back on the stream after a start, `Feed.backfill` reads the last trade
  this instance recorded of it (`list_trades(..., latest_recorded=True)`)
  and records what the venue's history states after it
  (`meridian.roles.data.backfill_restart`), once per subject per process.
  `Feed.read_licences` reads which of its own datasets a deployment admin
  has licensed (`list_datasets`), on start and each minute.
- **Settings**: the data role's order; with one environment and no key,
  only `sample_data` (`meridian.sample_data()`), a developer's.
- **No real response is committed.** Kraken asks its prior permission for any
  non-personal commercial use of its public data, so `tests/` and
  `src/kraken/synthetic/` hold synthetic exchanges, shaped exactly as Kraken
  sends its answers, with
  invented values; a developer's recordings stay outside the repository
  (`make e2e-recorded RECORDED=<dir> DAY=<a day it holds>`).
- **Declare each page with the levels it serves**, where its view is:
  `@pages.page(path, title, levels=[...])`. The dashboard shows a page under
  the buttons of its levels, and the SDK refuses any other session before
  the view runs. Declare no `tags`.
- Manage opens on the plugin's Summary, which core draws, with its raw
  records per kind. Build no summary page of your own.
- **A plugin at the edge keeps its raw records in its own storage and moves
  them past their window through the SDK** (`RawStore.tend`: a day's unit of
  `responses`, archived, kept or deleted as `responses_past_window` says,
  never by deleting files), and says what storage holds (`plugin.stored`).
  Declare no window setting of your own: the SDK declares
  `responses_window_days` and `responses_past_window`.
- **Never a setting from the environment** but the page's port: a setting is
  declared to the SDK (`declaration.py`) and read from `plugin.settings()`.
  `synthetic` is a developer's setting, shown only on a development
  deployment.

This file is for any coding agent working on the plugin, and is committed with
it for whoever works on it next. It is the canonical one: `CLAUDE.md` and the
`develop-live` skill lead Claude Code here rather than repeating it.
`.dockerignore` keeps all of them out of the image and the live instance.

## Checking it: `meridian plugin check`

Whatever in this file can be decided from the text is checked, not only
said: `meridian plugin check` holds the plugin to the rules every Meridian
plugin is built to (the template's
shape, `[tool.meridian]`, the kit linked and no raw colour, nothing from
another origin, settings declared rather than read from the environment, no
secret logged or put in a page, the deployment reached only through the SDK,
and tests). It needs no deployment and no session, and changes nothing. It
came in `meridian` 0.1.15; with an older one, the person runs
`meridian upgrade`.

- **Run `meridian plugin check` after each change.** Exit 0: every rule
  holds. Exit 1: at least one does not. Each failure names the rule, the file
  and line, and what to write instead: fix each one as it says, then run it
  again, until it exits 0. Never work around a rule; if one seems wrong for
  this plugin, tell the person.
- **`meridian plugin check --run-tests`** also runs the tests under `tests/`
  with pytest, in the plugin's `.venv` if it has one, otherwise with the
  `python3` on the PATH, which needs the plugin and pytest installed
  (`pip install -e . pytest`). `tests/test_data_role.py` asks the pages under
  Manage, Open and View with `meridian.testing.PageClient`, and the operation
  they send against a stand-in for the sidecar; replace its tests as you
  replace the pages, and add one for each page and each operation.
- The plugin's CI (`.github/workflows/check.yaml`) runs the same
  `meridian plugin check --run-tests` on every push.

What the check cannot decide stays advice, below: which component fits, the
page's layout, custom properties the kit does not define, figures as strings,
and names.

## Building its pages: the kit

Build every page with Open Meridian's plugin UI kit, and nothing else for its
look. Then it looks like the rest of the platform, follows each person's
colour scheme, light or dark, and their market-direction convention, and
needs no design work. The kit is plain CSS and web components: it works from
plain HTML, as the templates write it, and from React, Vue or Svelte alike.

**It is linked for you.** Each page's template, under `templates/`, is a
Jinja2 template that extends the SDK's base template,
`{% extends "meridian/base.html" %}`, which links the kit from the path the
dashboard serves it at on this plugin's own host and draws the page's heading
and tab row (the kit drops both when the dashboard frames the page and draws
its own). A template fills three blocks: `content`, the page itself;
`head_actions`, buttons marked `data-om-action="<id>"`, which the dashboard
draws in its header; and `status`, an `<om-status data-om-header>` it draws
beside the plugin's name. `pages.render("x.html", ...)` renders it, every
value escaped, with `caller` and `level` (admin, write or read) in it; a
template adapts by `{% if level == "write" %}`, and `{% include %}` and
macros share pieces between pages. A form that posts puts `{{ csrf_input }}`
inside it (a script sends `request.csrf_token` as `X-CSRF-Token`): every
request but GET and HEAD without this plugin's token is refused before the
view runs, so another site's page cannot act here as the person. A GET
changes nothing.

Never copy the kit into the plugin, and never load it, or anything else for
the page, from another origin or a CDN.

**Which component for what:**

| For | Use |
|---|---|
| A table of records | `<om-grid row-key="…">`: set `columns`, then `setRows(rows)`; `upsert(rows)` replaces rows by key in place; figures sort exactly |
| A stream: thousands of rows, many changes a second | `<om-grid high-rate>`: only the rows in view are drawn, only changed cells are touched, and they flash up or down; `freeze-sort` stops rows jumping while streaming |
| Live data from the plugin's server | `<om-live src="events" snapshot="snapshot.json" for="grid-id">`: follows server-sent events in sequence, and reads the snapshot again after a gap or a reconnect, so nothing is missed |
| The date the figures are as of | `<om-asof>` |
| Choosing an instrument | `<om-instrument-picker src="…" asof="…">`, searching through the plugin's own server |
| A time series | `<om-chart type="line">` (or `bar`), `series` set in script |
| Several views on one page, resizable and rearrangeable | `<om-panels layout-id="…">`, a `data-panel` child per view; each person's arrangement is remembered |
| Everything else | The kit's classes: `.page`, `.page-head`, `.panel` and `.panel-body`, `.tiles`, `.tabs`, `.field`, `.filters`, `.notice`, `.badge`, `button.primary` and `.danger`, `table` and `.num`, `.empty-state` |

Give a component its data as JSON inside it, `<script
type="application/json">{{ grid | tojson }}</script>`, which needs no script of the
page's; or set it (`columns`, `rows`, `series`) as properties, in a
`customElements.whenDefined(...)` callback. The kit's README
(open-meridian/meridian-ui) documents every component, attribute and event.

**Colour.** Only the kit's custom properties, never a hex, `rgb()`, `hsl()` or
a colour's name: not in a stylesheet, an inline style, an SVG or a script. A
person chooses their scheme and their deployment's administrator may add
schemes; a raw colour is one no scheme can change and no contrast check has
seen. Prefer a class to a property, and a property to anything else:

- surfaces `--page`, `--card`, `--hover`; text `--ink`, `--ink-soft`,
  `--ink-faint`; edges `--line`, `--line-soft`, `--line-strong`
- `--accent` and `--accent-wash`; `--primary` and `--primary-ink`
- status, which never changes meaning: `--good`, `--danger`, `--warn-ink`,
  `--violet`, each with its `-wash`
- **market direction:** `--buy` for a buy, a rise or a gain, and `--sell` for a
  sell, a fall or a loss, with `--buy-wash` and `--sell-wash`. Never green and
  red, and never `--good` and `--danger`, for a price move: where a person
  reads red as up (China, Japan, Korea, Taiwan) the kit swaps buy and sell for
  them. In markup, `.buy-ink` and `.sell-ink`, `.badge.buy` and `.badge.sell`;
  in a grid, a column's `tone: "sign"`.

Spacing, radii, shadows and type are the kit's too: `var(--space-1)` to
`var(--space-10)`, `var(--radius)`, `var(--shadow)`, `var(--sans)`,
`var(--mono)`.

**No chrome, no theme code.** The dashboard frames the page and draws the
plugin's name, its tab row, the way back to the dashboard and the person. The
page draws only its content, which the base template puts inside `<main
class="page">`: no header bar, navigation, logo, sign-in or sign-out, and no
light and dark switch. The kit applies the
person's theme, which the frame hands it, with no code of the page's.

**Money is exact.** Send prices and quantities to the page as decimal strings
and show them as sent; never `parseFloat` one. The grid sorts them exactly.

**The kit's rules, which a page keeps too:** no raw colour; no custom
property the kit does not define, other than the page's own layout ones; the
page reaches only its own origin, the plugin's server, which proxies anything
further; figures are strings, never floats.

**Where the kit is not served.** Until every dashboard serves `/.meridian/ui/`,
build pages that work without it, as the templates do: put a plain `<table>`
inside `<om-grid>` (a browser shows it as it is, and the kit's grid replaces
it), give components their data as JSON inside them, and make actions plain
forms. Without the kit the page is unstyled, but everything on it works.

A short page, whole: the view, in `page.py`,

```python
COLUMNS = [
    {"key": "symbol", "label": "Instrument"},
    {"key": "quantity", "label": "Quantity", "type": "decimal", "group": True},
    {"key": "market_value", "label": "Market value", "type": "decimal", "group": True},
    {"key": "day_pnl", "label": "Day P&L", "type": "decimal", "group": True, "tone": "sign"},
]


@pages.page("/positions", "Positions", levels=["write", "read"])
def positions(request: meridian.Request) -> str:
    return pages.render("positions.html", grid={"columns": COLUMNS, "rows": []})
```

and its template, `templates/positions.html`:

```html+jinja
{% extends "meridian/base.html" %}
{% block head_actions %}
<om-live src="events" snapshot="positions.json" for="positions"></om-live>
{% endblock %}
{% block content %}
<p class="muted">Every account you may read here.</p>
<section class="panel">
  <om-grid id="positions" row-key="position_id" high-rate sort="market_value:desc" caption="Positions">
    <script type="application/json">{{ grid | tojson }}</script>
    <table><tr><th>Instrument</th><th>Quantity</th><th>Market value</th></tr></table>
  </om-grid>
</section>
{% endblock %}
```

The plugin's server answers `positions.json` with `{ "sequence": "41", "rows":
[…] }` and `events` as server-sent events, each `id: <sequence>` and `data:
{ "rows": […] }` carrying whole records; `om-live` feeds them to the grid.

## Developing it live

On a Meridian deployment installed for development, `meridian plugin dev`
runs this plugin as you write it: each saved file is sent, the plugin's process
restarts on it in the same pod, and it is running again in about a second. The
pod, its sidecar and what it is allowed to do stay as they were.

Everything here runs on the person's own session with the deployment, and is
theirs.

### Before starting

- `meridian --version` is 0.1.21 or later. Older ones have no `--level` on
  `plugin open`, before 0.1.15 no `plugin check`, and before 0.1.3 no
  `plugin dev`: the person runs `meridian upgrade`.
- The person has run `meridian connect` (with the address, for a deployment
  not on this machine). You cannot do it for them: it signs in through their
  browser. `meridian plugin list` says whether the
  session is there: it lists the catalogue, or exits **3**. Whenever any
  command exits 3, the session is missing or has lapsed. Stop, tell the person
  to run the `meridian connect` the command printed, and carry on once they
  have. There is no `meridian status`.
- The deployment was installed for development (`meridian up --development`).
  Elsewhere `plugin dev` is refused, and nothing is wrong with the plugin.

### Start the loop

The instance is called `kraken` below. Use whatever the person
wants it called, and the same name in every command.

**The first time an instance is launched, the person approves what it asks
for.** Show them the `roles` in `pyproject.toml`'s `[tool.meridian]`
and ask. Only once they say yes, pass `--yes`; never pass it to get past a
question they have not answered. An instance that is live already asks
nothing.

Run it in the background, and keep it running for the whole session:

```sh
mkdir -p .meridian
meridian plugin dev --instance kraken --yes --json > .meridian/dev.jsonl 2> .meridian/dev.err
```

Its output goes under `.meridian/` on purpose. `plugin dev` sends every file
in this directory that changes, except `.meridian/` and what `.dockerignore`
names. Anywhere else in this directory, its own output would be sent to the
plugin as a change, again and again. Not under your own agent's directory
(`.claude/`, `.cursor/` and the like) either: some agents guard theirs, and
writing there needs a permission a session may not have. `.meridian/` is
git-ignored, since it is this session's, not the plugin's.

`.meridian/dev.jsonl` gets one JSON object a line:

| `event` | Means |
|---|---|
| `seeded` | The live folder was filled from the plugin's image, the first time it runs live |
| `sent` | This process sent a change; `revision` is the number it was given |
| `synced` | The sidecar wrote it |
| `restarted` | The plugin's process started on that revision |
| `ready` | It connected to its sidecar again: that revision is running |
| `crashed` | It stopped with an error. `traceback` has the last of what it printed |
| `exited` | It stopped by itself, without an error |
| `refused` | The sidecar refused it something; `reason` says what |

Wait for the first `ready` before changing anything. `.meridian/dev.err` says
what it is doing, and why it stopped if it did. The first run builds and
uploads the plugin's image, which takes a minute or two.

### Change something

1. Edit and save. There is nothing to run: the save is the deploy.
2. Find the `sent` line after your save, and its `revision`, R.
3. Wait for `ready` or `crashed` at R. Nothing about R is known before then.
4. On `crashed`, read its `traceback`, fix the cause, and save again: the next
   revision replaces it. Nothing needs restarting.

Several saves close together can land as one revision. Read the newest `sent`.

### Check it

Ask the question that answers what you changed:

| To know | Run |
|---|---|
| What a page shows, as the person is served it | `meridian plugin open --instance kraken --level manage --print /` for Connection, and `--level manage --print /datasets` for Datasets: any path on the plugin, at a level it is declared with |
| What the plugin printed or logged since your change | `meridian plugin logs --instance kraken --since <R-1>` |
| What the sidecar refused it, or what else happened | `meridian plugin events --instance kraken --since <R-1> --json` |
| What the person sees in a browser | `meridian plugin open --instance kraken --level manage`: a link one browser opens once, at that level. Give it to the person, or open it in your browser pane |

`--level` is the home's button the session is opened by: `manage`, `open` or
`view`. Name it every time. A page answers 403 at a level it is not declared
with, and without `--level` the dashboard opens at the first level the person
holds, Manage before Open before View, so on a development deployment, where
they hold `admin`, `/` would be asked under Manage and refused.

`--print` exits non-zero when the plugin answers with an error, and prints what
it answered. Prefer it to a browser for checking your own work: it needs no
browser and gives the same page every time.

### What a save cannot change

- **What it is allowed to do.** A `refused` event is its grants working, not a
  bug to code around. Adding a role to `pyproject.toml` changes nothing
  live: it takes a new version, and a person approves it.
- **Its dependencies.** The live code runs on the image the instance was
  launched from. A new package in `pyproject.toml` needs a new version.

Tell the person when a change needs either, rather than looking for a way
round it.

### Release it

When the person is satisfied:

1. Run `meridian plugin check --run-tests`, and fix what fails until it
   exits 0.
2. Raise `version` in `pyproject.toml`. A version is never replaced.
3. Show the person the roles again, and get their yes.
4. Run `meridian plugin dev --release --instance kraken --yes`.

That uploads this directory as that version and runs it in place of the live
instance. It is then an ordinary version in the deployment's catalogue.

### Stop

Stop the background `plugin dev`. The instance keeps running, live, as it was.
`meridian plugin stop kraken` ends it, which is the person's call.
