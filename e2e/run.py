"""`make e2e` and `make e2e-recorded`: the plugin end to end on core's plugin
harness (contracts v18 to v20), with sample data, beside a reader
(e2e/reader.py).

1. Launched: the plugin registers its catalogue; the deployment admin's tool
   lists its three datasets, `daily`, `live` and `trades`, each on the UTC day
   ending at 00:00, with their modes.
2. Sample data on: the plugin reads its listing and mints no record for
   any asset (the first build minted one per asset); the venue, which the
   harness's deployment does not hold (it has no platform), reported
   missing. The reader then names bitcoin as a custodian's book holds it,
   by its CAIP-19 and the custodian's symbol, and the dollar and the euro by
   ISO 4217.
3. Licensed and entitled: the admin licenses the three datasets and entitles
   the reader to them, the broker reloaded with each.
4. A close wanted: the reader reads the custodian's bitcoin's closes for a
   day nothing has recorded; the lake asks the plugin, which reads the
   record (W3.6, a data plugin's from contract v18 as ruled 2026-10-10), names it
   Kraken's XXBT by its CAIP-19, joins its own code to it, and records
   XXBTZUSD's close in dollars and XBTUSDC's on USDC's own instrument --
   resolved then, the one record it mints -- exactly as the venue stated
   them, on that business date, each naming its raw record and the venue as
   reported; the reader reads both, and hears them -- following BTC's
   prices, trades and quotes, whose latest quote stands as a want of the
   live dataset. No record was minted for an asset no subject is.
5. Declined, and a rate: a read of the dollar's closes, which no pair's base
   is, is declined as not covered; the euro's, recorded from EUR/USD in
   dollars: an FX rate on a currency's cash instrument.
6. Live: a read of BTC's latest on the live dataset stands as a want, which
   the plugin keeps current -- the last trade's price and the best bid and
   offer of each product -- until the lake withdraws it.
7. Streamed (contract v19): the standing want puts BTC's pairs on Kraken's
   v2 stream; the synthetic venue drops the first connection, the plugin
   opens it again and reads the trades it missed from Kraken's `Trades`, so
   every trade is recorded once in `trades`, its aggressor the side that took
   liquidity (Kraken's taker side as sent), eligible for every statistic,
   exactly as stated, with no business date; the reader reads them over the
   day, and after the watermark it saw, and hears them; and reads each
   pair's latest quote in `live`, with its sizes.
8. Parity: the plugin's two read tools answer through the deployment's MCP
   what its two pages show, the data role's fields under its names, the
   stream's session among them, and each dataset licensed (contract v20).
9. Its raw responses are in its granted storage, the book's depth among
   them as the stream sent it (open question 232), and `store lake` prints
   each row kept, numbered with no holes in each dataset, the wants asked,
   answered, declined and withdrawn, and the venue's miss.
10. A restart's gap (contract v20): with BTC's products on the stream still,
   the plugin restarted reads the last trade it recorded of each subject from
   the lake (ListTrades, latest_recorded) and the venue's history after it;
   run after step 8 and before step 9 waits for the live want's withdrawal.

Run from the repository's root by the Makefile, which builds the image,
copies the harness out and writes the plugins' compose file first, and
exports what the compose files read. Standard library only.
"""

import json
import re
import subprocess
import sys
import time

VENUE = "kraken"
NAME = "Kraken"
#: `make e2e-recorded` names the day its recorded exchanges hold
#: (`--day=YYYY-MM-DD`): the run then reads that day, and holds the rows to
#: their shape rather than to the synthetic exchange's values.
DAY = [a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--day=")]
EXACT = not DAY
CLOSED = DAY[0] if DAY else "2026-10-08"
LOG = ".e2e/runner.log"
#: A product quoted in dollars, and one quoted in USDC.
FIAT_PRODUCT, STABLE_PRODUCT = "XXBTZUSD", "XBTUSDC"
#: The harness's compose files and this plugin's, and any the Makefile adds
#: (`make e2e-recorded`'s e2e/recorded.yaml), given as arguments.
COMPOSE = ["docker", "compose", "-p", f"{VENUE}-e2e", "-f", ".e2e/harness/compose.yaml",
           "-f", ".e2e/harness/plugins.yaml", "-f", "e2e/plugin.yaml",
           *[a for a in sys.argv[1:] if not a.startswith("--day=")]]
#: What the synthetic exchange states, which the rows must carry exactly.
CLOSES = {"XXBTZUSD": "62001.40000", "XBTUSDC": "62006.75"}
LAST = {"XXBTZUSD": "61988.90000", "XBTUSDC": "62006.75"}
#: The euro's close in dollars that day (ZEURZUSD): an FX rate.
EUR_CLOSE = "1.0925"
#: The assets no subject is, for which the first build minted a record each.
UNASKED = r"(?<![A-Z])(X?ETH|TKN|QDT|PLY)(?![A-Z])"
#: The raw files the stream's depth is kept in (open question 232).
DEPTH_FILES = ("book.jsonl",)
#: The day the synthetic stream's trades are on, as a UTC range.
TRADES_FROM, TRADES_UNTIL = 1791590400 * 10**9, 1791676800 * 10**9
#: Each trade the synthetic stream and history state, by its row key, with
#: the side that took liquidity: Kraken's taker side as sent. 110938303 to
#: 110938306 are read back from `Trades` when the stream opens again.
TRADES = {"XXBTZUSD:t:110938301": "SELL", "XXBTZUSD:t:110938302": "BUY",
          "XXBTZUSD:t:110938303": "BUY", "XXBTZUSD:t:110938304": "SELL",
          "XXBTZUSD:t:110938305": "BUY", "XXBTZUSD:t:110938306": "SELL",
          "XXBTZUSD:t:110938307": "BUY", "XBTUSDC:t:5502": "SELL", "XBTUSDC:t:5503": "SELL"}
#: 110938302 exactly as the stream stated it, its JSON numbers read as text.
STATED = ("XXBTZUSD:t:110938302", "61990.20000", "0.01250000")
#: Each pair's latest best bid and offer, with their sizes.
QUOTES = {"XXBTZUSD": ("61991.7", "0.92000000", "61991.8", "0.33000000"),
          "XBTUSDC": ("62007.10", "0.10000000", "62007.40", "0.25000000")}


class Failed(Exception):
    pass


def log(text):
    with open(LOG, "a", encoding="utf-8") as kept:
        kept.write(text + "\n")


def compose(*args, check=True):
    done = subprocess.run(COMPOSE + list(args), capture_output=True, text=True, timeout=600)
    log(f"$ compose {' '.join(args)[:300]}\n{done.stdout[-4000:]}{done.stderr[-2000:]}")
    if check and done.returncode != 0:
        raise Failed(f"compose {' '.join(args)[:200]}: {(done.stdout + done.stderr).strip()[-600:]}")
    return done


def runner(*args, check=True):
    done = compose("run", "--rm", "-T", "runner", *args, check=check)
    return done.stdout if check else done


def must(condition, why):
    if not condition:
        raise Failed(why)


def until(seconds, attempt, what):
    deadline = time.monotonic() + seconds
    last = None
    while True:
        try:
            answer = attempt()
        except Failed as failed:
            answer, last = None, failed
        if answer:
            return answer
        if time.monotonic() > deadline:
            raise Failed(f"{what}, in {seconds} seconds" + (f": {last}" if last else ""))
        time.sleep(2)


def page(instance, level, path):
    said = runner("page", "--instance", instance, "--level", level, path)
    status, _, body = said.partition("\n")
    must(status.strip() == "200", f"{instance} {path} answered {said[-600:]}")
    return body


def read(path):
    return json.loads(page("reader", "read", path))


def call(tool, arguments, *outcomes):
    done = runner("mcp", "call", tool, json.dumps(arguments), check=False)
    try:
        answer = json.loads(done.stdout)
    except ValueError:
        raise Failed(f"{tool}: no answer: {(done.stdout + done.stderr)[-400:]}") from None
    must(answer.get("outcome") in outcomes,
         f"{tool} answered {answer.get('outcome')}, not {outcomes}: {done.stdout[-700:]}")
    return answer


def said(listed):
    """The identifiers each listed record carries, without its ID: a minted
    ID is random, and can spell an asset's code (LCL-...8ETH7...)."""
    return "\n".join(line.partition("\t")[2] for line in listed.splitlines())


def instrument(listed, pattern, required=True):
    for line in listed.splitlines():
        instrument_id, _, identifiers = line.partition("\t")
        if re.search(pattern, identifiers):
            return instrument_id
    if not required:
        return ""
    raise Failed(f"no record listed matches {pattern}: {listed}")


def run():
    started = time.time()
    compose("--profile", "runner", "down", "-v", "--remove-orphans", check=False)
    compose("up", "-d")
    for instance in (VENUE, "reader"):
        runner("ready", "--instance", instance)
    runner("grant", "--instance", "reader", "--level", "read", "--role", "reporting")
    runner("grant", "--instance", VENUE, "--level", "admin")
    runner("mcp", "connect", "--covers", "deployment_admin", "--covers", f"{VENUE}:admin")
    tools = runner("mcp", "list").split()
    named = {t.rsplit("__", 1)[-1]: t for t in tools}
    for name in ("dashboard__list_datasets", "read_connection", "read_datasets"):
        must(name.rsplit("__", 1)[-1] in named, f"step 1, {name} is listed: {tools}")

    # 1. The catalogue, as the deployment admin's tool lists it.
    def datasets():
        held = {d["dataset"]: d for d in
                call("dashboard__list_datasets", {}, "read", "unchanged")["data"]["datasets"]}
        return held if {f"{VENUE}:{k}" for k in ("daily", "live", "trades")} <= set(held) else None
    held = until(90, datasets, "step 1, the three datasets were not listed")
    for key, modes in (("daily", ["pull", "push"]), ("live", ["pull", "stream"]),
                       ("trades", ["pull", "stream"])):
        entry = held[f"{VENUE}:{key}"]["catalogue_entry"]
        must(entry["modes"] == modes and entry["day_time_zone"] == "Etc/UTC"
             and entry.get("day_end_minute", 0) == 0, f"step 1, {key}'s entry: {entry}")

    # 2. Sample data: the listing read, no record minted for any asset;
    # then the reader's records, as a custodian's book holds them.
    runner("settings", "--instance", VENUE, "sample_data=true")
    until(90, lambda: call(named["read_datasets"], {}, "read", "unchanged")["data"]
          ["products_listed"] >= 5, "step 2, the listing was not read")
    listed = runner("instruments")
    log("instruments, the listing read:\n" + listed)
    must(not re.search(UNASKED, said(listed)) and "USDC" not in listed and "slip44" not in listed,
         f"step 2, no record minted for an asset no subject is: {listed}")
    ids = read("/resolve")
    btc, usd, eur = ids["btc"], ids["usd"], ids["eur"]

    # 3. Licensed and entitled.
    runner("licence", f"{VENUE}:daily", "kept=true", "retention_days=0", "derived_use=true",
           "display=true", "personal_use=false", f"note={NAME}'s market data terms.")
    runner("licence", f"{VENUE}:live", "kept=true", "retention_days=2", "display=true",
           "personal_use=false", "note=Kept two days.")
    runner("licence", f"{VENUE}:trades", "kept=true", "retention_days=2", "display=true",
           "personal_use=false", "note=Kept two days.")
    runner("grant", "--instance", "reader", "--level", "read", "--role", "signal")
    for key in ("daily", "live", "trades"):
        runner("entitle", "--instance", "reader", f"{VENUE}:{key}", "note=The e2e's reader.")

    # 4. A close wanted, recorded against the want, read and heard.
    daily = f"/prices?subject={btc}&date={CLOSED}&kind=close&dataset={VENUE}:daily"
    first = read(daily)
    # The lake asks the plugin at once: unanswered as asked, or, where the
    # plugin's answer is already in, as the source being silent so far.
    must(not first["prices"] and {u["reason"] for u in first["unanswered"]}
         <= {"UNANSWERED_REASON_ASKED_SOURCE", "UNANSWERED_REASON_SOURCE_SILENT"}
         and first["unanswered"], f"step 4, a day not recorded is asked of the plugin: {first}")
    closes = until(90, lambda: (lambda r: r if len(r) >= (2 if EXACT else 1) else None)(
        read(daily)["prices"]),
                   "step 4, the plugin did not record the closes wanted")
    by_product = {p["row_key"].split(":")[0]: p for p in closes}
    for product, amount in CLOSES.items():
        row = by_product[product] if EXACT else by_product.get(product)
        if row is None:
            continue
        must((row["amount"] == amount or not EXACT) and row["business_date"] == CLOSED,
             f"step 4, {product}'s close as the venue stated it: {row}")
        must(row["venue_id"] == "" and row["unconverted"] == [f"{VENUE}:venue"],
             f"step 4, the venue not held, named as reported: {row}")
        must(row["raw"].startswith("responses/"), f"step 4, its raw record: {row}")
    dollars = by_product.get(FIAT_PRODUCT) or next(iter(by_product.values()))
    listed = runner("instruments")
    log("instruments, after the want:\n" + listed)
    # A recording may hold no product quoted in USDC (Coinbase delisted
    # BTC-USDC): then nothing names USDC, and nothing is asserted of it.
    usdc = instrument(listed, r"(?<![A-Z])USDC(?![A-Z])", required=EXACT)
    must(not re.search(UNASKED, said(listed)),
         f"step 4, no record minted for an asset no subject is: {listed}")
    must(dollars["instrument_id"] not in ("", usdc, btc),
         f"step 4, a dollar price names the dollar's cash instrument: {dollars}")
    stable = by_product.get(STABLE_PRODUCT, {"instrument_id": usdc, "currency_code": ""})
    must(stable["instrument_id"] == usdc and stable["currency_code"] == "",
         f"step 4, a USDC price on USDC's own instrument, never a currency: {stable}")
    # Followed: the reader's receive reads what the lake holds for BTC, and
    # its latest on each dataset is asked of the plugin -- the daily
    # dataset's being the past week's days.
    read(f"/follow?subject={btc}")
    until(60, lambda: [h for h in read("/heard")["heard"] if h["dataset"] == f"{VENUE}:daily"],
          "step 4, the reader did not hear the closes")

    # 5. Declined: no product's base is the dollar. And an FX rate: the euro's
    #    cash instrument priced in dollars, as Kraken's EUR/USD states it.
    dollar = f"/prices?subject={usd}&date={CLOSED}&kind=close&dataset={VENUE}:daily"
    read(dollar)
    euro = f"/prices?subject={eur}&date={CLOSED}&kind=close&dataset={VENUE}:daily"
    read(euro)
    # A developer's recording may hold no EUR/USD day (those of 2026-10-03
    # do not): there the euro is answered as declined, never made up.
    def euro_answered():
        said = read(euro)
        return said if said["prices"] or (not EXACT and said["unanswered"]) else None
    rate = until(90, euro_answered, "step 5, the plugin did not record the rate")["prices"]
    must((not rate and not EXACT) or (
         len(rate) == 1 and (rate[0]["amount"] == EUR_CLOSE or not EXACT)
         and rate[0]["row_key"].startswith("ZEURZUSD:")
         and rate[0]["currency_code"] in ("USD", "")), f"step 5, the euro in dollars: {rate}")

    # 6. Live: kept current while it stands, then withdrawn.
    live = f"/prices?subject={btc}&dataset={VENUE}:live"
    read(live)
    # The lake answers the latest per subject, dataset, kind and venue, so a
    # read gives one product's last price; `store lake` holds every one.
    def live_rows():
        rows = read(live)["prices"] + [h for h in read("/heard")["heard"]
                                       if h["dataset"] == f"{VENUE}:live"]
        return [r for r in rows if r["kind"] == "PRICE_KIND_LAST"]
    lasts = until(90, live_rows, "step 6, the plugin did not record the live prices")
    for row in lasts:
        stated = LAST.get(row["row_key"].split(":")[0])
        must((row["amount"] == stated or not EXACT) and not row["business_date"],
             f"step 6, a last price as stated, keyed by its instant: {row}")

    # 7. Streamed: every trade once, the gap read back; the latest quotes.
    def all_trades():
        if EXACT:
            asked = f"/trades?subject={btc}&from={TRADES_FROM}&until={TRADES_UNTIL}"
        else:
            asked = f"/trades?subject={btc}&after={VENUE}:trades:0"
        answer = read(asked)
        keys = {t["row_key"] for t in answer["trades"]}
        return answer if (keys >= set(TRADES) if EXACT else keys) else None
    answer = until(120, all_trades, "step 7, the stream's trades, and the gap, were not recorded")
    trades = answer["trades"]
    must(len({t["row_key"] for t in trades}) == len(trades)
         and all(t["version"] == 1 for t in trades), f"step 7, each trade once: {trades}")
    for trade in trades:
        side = TRADES.get(trade["row_key"]) if EXACT else None
        must(trade["dataset"] == f"{VENUE}:trades" and not trade["business_date"]
             and trade["aggressor"] in ("AGGRESSOR_BUY", "AGGRESSOR_SELL")
             and (side is None or trade["aggressor"] == f"AGGRESSOR_{side}")
             and trade["eligible"] == ["ELIGIBLE_ELIGIBLE"] * 4
             and trade["venue_id"] == "" and trade["unconverted"] == [f"{VENUE}:venue"],
             f"step 7, a trade as the venue stated it, its aggressor the taker's side: {trade}")
        stable = trade["row_key"].startswith(f"{STABLE_PRODUCT}:")
        quoted = (trade["currency_code"] == "USD" if EXACT
                  else bool(trade["currency_code"] or trade["instrument_id"]))
        must(trade["instrument_id"] == usdc if stable else quoted,
             f"step 7, a trade's price in its product's quote asset: {trade}")
    if EXACT:
        [stated] = [t for t in trades if t["row_key"] == STATED[0]]
        must((stated["amount"], stated["quantity"]) == STATED[1:], f"step 7, exact: {stated}")
        later = read(f"/trades?subject={btc}&" + "&".join(
            f"after={p.replace('|', ':')}" for p in answer["watermark"]))
        must(later["trades"] == [] and answer["watermark"],
             f"step 7, nothing recorded after the watermark the reader saw: {later}")
    until(60, lambda: read("/heard")["trades"], "step 7, the reader did not hear the trades")

    def latest_quotes():
        quotes = {q["row_key"].split(":")[0]: q for q in read(f"/quotes?subject={btc}")["quotes"]}
        if EXACT:
            return quotes if all(
                product in quotes and (quotes[product]["bid"], quotes[product]["bid_quantity"],
                                       quotes[product]["ask"], quotes[product]["ask_quantity"])
                == said for product, said in QUOTES.items()) else None
        return quotes or None
    quotes = until(90, latest_quotes, "step 7, each product's latest quote was not recorded")
    must(all(q["dataset"] == f"{VENUE}:live" and not q["business_date"] and (q["bid"] or q["ask"])
             for q in quotes.values()), f"step 7, quotes in the live dataset: {quotes}")
    streamed = call(named["read_connection"], {}, "read", "unchanged")["data"]
    must(streamed["stream_opened"] >= (2 if EXACT else 1)
         and streamed["stream_dropped"] >= (1 if EXACT else 0) and streamed["stream_messages"] > 0,
         f"step 7, the stream opened, dropped and opened again: {streamed}")
    # Contract v27: the stream's heartbeat, which confirms every quote in
    # force, recorded as the live dataset's liveness, never a row; the reader
    # hears it, and the lake's listing holds it beside the declared delay,
    # none for a real-time feed.
    def alive():
        heard = [h for h in read("/heard")["liveness"] if h["dataset"] == f"{VENUE}:live"]
        listed = {d["dataset"]: d for d in read("/datasets")["datasets"]}
        log(f"liveness heard: {heard[-3:]}; listed: {listed}")
        live = listed.get(f"{VENUE}:live", {})
        return (heard, live) if heard and live.get("liveness") else None
    heard, live = until(90, alive, "step 7, the live dataset's liveness was not recorded")
    must(all(h["alive_at_ns"] > 0 for h in heard) and live["declared_delay_ns"] == 0,
         f"step 7, the stream's liveness, and no declared delay: {heard[-3:]}, {live}")

    # 8. Parity: each read tool answers what its page shows.
    connection = call(named["read_connection"], {}, "read", "unchanged")["data"]
    must(connection["mode"] == "Sample data" and connection["venue"] == NAME
         and connection["credentials"] == [] and connection["entitled_at_vendor"]
         and connection["venue_held"] is False and connection["calls"] > 0,
         f"step 8, read_connection: {connection}")
    shown = page(VENUE, "admin", "/")
    must("Sample data: the plugin answers from recorded responses" in shown
         and "No key needed" in shown and NAME in shown,
         "step 8, the Connection page shows the same")
    served = call(named["read_datasets"], {}, "read", "unchanged")["data"]
    must([d["dataset"] for d in served["served"]]
         == [f"{VENUE}:daily", f"{VENUE}:live", f"{VENUE}:trades"]
         and served["products_mapped"] >= 3 and (served["subjects_named"] == 3 if EXACT else served["subjects_named"] >= 1)
         and served["reads_instruments"] is True
         and sum(d["recorded"] for d in served["served"]) >= 2,
         f"step 8, read_datasets: {served}")
    def licensed():
        rows = call(named["read_datasets"], {}, "read", "unchanged")["data"]["served"]
        return rows if all(d["licensed"] for d in rows) else None
    until(90, licensed, "step 8, read_datasets did not say each dataset licensed")
    shown = page(VENUE, "admin", "/datasets")
    must("Not licensed yet" not in shown and "Licensed" in shown,
         "step 8, the Datasets page says each dataset licensed")
    must(f"{served['products_mapped']} of {served['products_listed']} products mapped" in shown,
         "step 8, the Datasets page shows the same")
    shown = page(VENUE, "admin", "/")
    must(" on it; " in shown or "Nothing stands to stream." in shown,
         "step 8, the Connection page shows the stream's session")

    # 10. A restart's gap (contract v20), while bitcoin's pairs stand to
    # stream under the wants above: the plugin, restarted, hears them again
    # (the lake delivers a standing want again each minute) and, before
    # streaming, reads the last trade it recorded of each subject it streams
    # from the lake (ListTrades, latest_recorded) and the venue's history
    # after it, the call answered rather than refused. Run here, before step
    # 9 waits for the live want's withdrawal: until contract v24 it ran last,
    # standing a want of USDC's latest live price, which nothing had
    # recorded; from v24 the lake never wants a provisional record (W10.6,
    # W10.7), and Kraken's USDC, named by its code alone as Kraken's own
    # instrument, is the deployment's provisional record, so nothing would
    # stand to stream. Bitcoin's rows held, a read of it asks nothing again.
    def gaps():
        said = compose("logs", "--no-color", VENUE).stdout
        must("a restart's gap not read back" not in said, f"step 10, refused: {said[-800:]}")
        return len(re.findall(r"a restart's gap read back: \d+ trades for \d+ subjects", said))
    until(90, lambda: call(named["read_connection"], {}, "read", "unchanged")["data"]
          ["stream_state"] != "off", "step 10, nothing stood to stream")
    before = until(60, gaps, "step 10, the gap was not read before the stream opened")
    compose("restart", VENUE)
    until(180, lambda: gaps() > before or None,
          "step 10, the restarted plugin did not read its gap back")

    # 9. Raw responses kept, and the lake's record.
    kept = compose("exec", "-T", VENUE, "python", "-c",
                   "from meridian import edge; "
                   "print(sum(1 for p in (edge.storage_dir() / 'responses').rglob('*') if p.is_file()))")
    must(int(kept.stdout.strip() or 0) >= 5, f"step 9, raw responses in storage: {kept.stdout}")
    # Depth (open question 232): the book's messages kept raw in the stream's
    # files, in no lake kind; a recording kept before 0.8.0 holds none.
    if EXACT:
        depth = compose("exec", "-T", VENUE, "python", "-c",
                        "import json; from meridian import edge; "
                        "print(json.dumps(sorted({p.name for p in "
                        "(edge.storage_dir() / 'responses').rglob('stream/*.jsonl') "
                        "if p.stat().st_size})))")
        must(set(DEPTH_FILES) <= set(json.loads(depth.stdout.strip() or "[]")),
             f"step 9, depth kept raw: {depth.stdout}")
    names = {k: v for k, v in {usdc: "USDC", btc: "BTC", usd: "USD", eur: "EUR"}.items() if k}

    def lake():
        lines = compose("run", "--rm", "-T", "store", "lake").stdout.split("\n")
        for instrument_id, name in names.items():
            lines = [line.replace(instrument_id, name) for line in lines]
        withdrawn = any(line.startswith(f"want|{VENUE}:live|withdrawn|") for line in lines)
        declined = any(line.startswith(f"want|{VENUE}:daily|declined|USD|") for line in lines)
        return lines if withdrawn and declined else None
    lines = until(240, lake, "step 9, the live want was not withdrawn, or the dollar not declined")
    log("store lake:\n" + "\n".join(lines))
    rows = [line.split("|") for line in lines if line.startswith(f"row|{VENUE}:daily|")]
    sequences = sorted(int(row[3]) for row in rows)
    must(sequences == list(range(1, len(sequences) + 1)) and len(sequences) >= (2 if EXACT else 1),
         f"step 9, daily's rows numbered from 1 with no holes: {sequences}")
    # A recording holding no EUR/USD day records the euro nothing (step 5).
    must({row[6] for row in rows} == ({"BTC", "EUR"} if EXACT else {"BTC"} | (
         {"EUR"} & {row[6] for row in rows})) and CLOSED in {row[9] for row in rows},
         f"step 9, each row BTC's or the euro's, each on its business date: {rows}")
    must(all(row[8] == "" and row[11] == "true" for row in rows),
         f"step 9, the venue left empty, a value as reported: {rows}")
    must(f"want|{VENUE}:daily|asked|BTC|0" in lines, f"step 9, the want asked: {lines}")
    must(any(re.fullmatch(rf"want\|{VENUE}:daily\|answered\|BTC(,BTC)*\|0", line) for line in lines),
         f"step 9, the want answered, a subject for each row: {lines}")
    for product in LAST if EXACT else []:
        for kind in ("last", "bid", "ask"):
            must(any(line.startswith(f"row|{VENUE}:live|price|") and f"|{product}:{kind}:" in line
                     for line in lines), f"step 9, {product}'s {kind} kept: {lines}")
    traded = [line.split("|") for line in lines if line.startswith(f"row|{VENUE}:trades|")]
    sequences = sorted(int(row[3]) for row in traded)
    must(sequences == list(range(1, len(sequences) + 1))
         and len(sequences) >= (len(TRADES) if EXACT else 1),
         f"step 9, trades' rows numbered from 1 with no holes, each once: {sequences}")
    must({row[6] for row in traded} == {"BTC"}, f"step 9, each trade BTC's: {traded}")
    must(any(line.startswith(f"row|{VENUE}:live|") and ":q:" in line for line in lines),
         f"step 9, the quotes kept in the live dataset: {lines}")
    must(any(line.startswith(f"miss|{VENUE}|") for line in lines),
         f"step 9, the venue's miss counted: {lines}")

    print(f"e2e OK in {int(time.time() - started)}s: on core's plugin harness, the catalogue's "
          "daily, live and trades datasets listed by the deployment admin's tool on the UTC day; "
          "the "
          "listing read with sample data, with no record minted for any asset, and the venue "
          "reported missing; the three datasets licensed and the reader entitled; a custodian's "
          "bitcoin, by its CAIP-19 and the custodian's symbol, read and named, and a day's "
          "closes wanted and recorded against the want, XXBTZUSD's in dollars and XBTUSDC's on "
          "USDC's own instrument, exactly, read and heard, no record minted for an asset no "
          "subject is; the dollar declined as not covered and the "
          "euro's rate in dollars recorded; bitcoin's "
          "live prices kept current until withdrawn; bitcoin's pairs streamed, the first "
          "connection dropped and opened again, the trades it missed read back from Trades, "
          "every trade recorded once with its aggressor, read over the day and after the "
          "watermark and heard, and each pair's latest quote with its sizes; read_connection "
          "and read_datasets answering what the pages show, each dataset licensed; raw "
          "responses in storage; and "
          "`store lake` numbering each dataset's rows with no holes, the wants and the miss; "
          "and restarted, its gap read back from the lake's last trade and the venue's history")


def main():
    open(LOG, "w").close()
    try:
        run()
    except (Failed, subprocess.TimeoutExpired, KeyError, ValueError, IndexError) as failed:
        print(f"e2e FAILED: {failed}; the run is in {LOG}, the components' logs in "
              ".e2e/components.log", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
