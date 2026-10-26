"""The e2e's reader: a `reporting` plugin on the SDK, standing in for the
reading roles, so the lake has someone whose reads it asks this plugin for.
It holds `custody` beside `reporting` only so that it can name the
instruments it asks about as a custodian's book would, by resolving their
identifiers (W3.1): bitcoin by its CAIP-19 and the custodian's symbol, never
resolved by Kraken (whose code for it is XXBT), a record the plugin names by
reading it (W3.6, a data plugin's from contract v18 as ruled 2026-10-10); and the
dollar and the euro by ISO 4217.

From contract v19 it holds `signal` too, which reads and hears trades and
quotes (`reporting` reads neither).

It is not the plugin, and is never built into its image: `make e2e` runs it
from this file in a container of the plugin's image, which carries the SDK,
beside the plugin on core's harness. It answers its page as JSON for the
harness's runner (`page --instance reader --level read PATH`):

  /resolve                                    the records' IDs, by name;
  /follow?subject=ID...                       hears prices, trades and quotes
                                              recorded for them, and the
                                              datasets' liveness (contract v27);
  /heard                                      what it heard: each row's dataset,
                                              row key, version, kind and amount,
                                              and each liveness;
  /datasets                                   the datasets it may read, each
                                              with its declared delay and the
                                              liveness the lake holds (v27);
  /prices?subject=ID[&date=D][&kind=K][&dataset=D]
                                              one read: its rows, and what it
                                              left unanswered and why;
  /trades?subject=ID&from=NS&until=NS         trades over a range of one day;
  /trades?subject=ID&after=PARTITION:SEQ...   trades recorded after a watermark;
  /quotes?subject=ID                          the latest quotes in force.
"""

import asyncio
import http.server
import json
import threading
import urllib.parse

import meridian
from meridian import Interface, Page, SourceChoice
from meridian.operations import as_decimal, as_money
from meridian.plugin.v1 import operations_pb2 as ops

PORT = 8088
LOOP = asyncio.new_event_loop()
ASKED = {
    "btc": [ops.Identifier(scheme="caip19", value="bip122:000000000019d6689c085ae165831e93/slip44:0"),
            ops.Identifier(scheme="symbol", value="BTC", source="e2e-custodian")],
    "usd": [ops.Identifier(scheme="iso4217", value="USD")],
    "eur": [ops.Identifier(scheme="iso4217", value="EUR")],
}
#: What a custodian's statement states beside an identifier (contract v24,
#: W3.7): a description and a currency, the minimum a record is minted from.
STATED = {"btc": ("Bitcoin", "USD")}


def trade_json(trade, caught_up=False):
    meta, money = trade.meta, as_money(trade.price)
    return {
        "dataset": meta.source.dataset,
        "venue_id": meta.source.venue_id,
        "row_key": meta.row_key,
        "version": meta.version,
        "business_date": meta.business_date,
        "amount": str(money.amount),
        "quantity": str(as_decimal(trade.quantity)),
        "instrument_id": money.instrument_id,
        "currency_code": money.currency_code,
        "aggressor": ops.Aggressor.Name(trade.aggressor),
        "eligible": [ops.Eligible.Name(getattr(trade.attributes.consolidated, f))
                     for f in ("high_low", "open", "close", "volume")],
        "unconverted": [u.scheme for u in meta.unconverted],
        "raw": meta.raw.key,
        "caught_up": caught_up,
    }


def quote_json(quote):
    meta = quote.meta
    side = lambda field: str(as_money(getattr(quote, field)).amount) if quote.HasField(field) else ""  # noqa: E731
    size = lambda field: str(as_decimal(getattr(quote, field))) if quote.HasField(field) else ""  # noqa: E731
    return {
        "dataset": meta.source.dataset,
        "row_key": meta.row_key,
        "business_date": meta.business_date,
        "bid": side("bid"), "bid_quantity": size("bid_quantity"),
        "ask": side("ask"), "ask_quantity": size("ask_quantity"),
        "raw": meta.raw.key,
    }


def watermark_json(watermark):
    return [f"{p.partition}|{p.sequence}" for p in watermark.partitions]


def liveness_json(item):
    return {"dataset": item.dataset, "venue_id": item.venue_id, "alive_at_ns": item.alive_at_ns}


def price_json(price):
    meta, money = price.meta, as_money(price.price)
    return {
        "dataset": meta.source.dataset,
        "venue_id": meta.source.venue_id,
        "row_key": meta.row_key,
        "version": meta.version,
        "business_date": meta.business_date,
        "kind": ops.PriceKind.Name(price.kind),
        "amount": str(money.amount),
        "instrument_id": money.instrument_id,
        "currency_code": money.currency_code,
        "unconverted": [u.scheme for u in meta.unconverted],
        "raw": meta.raw.key,
    }


class Reader:
    def __init__(self, plugin):
        self.plugin = plugin
        self.heard = []
        self.trades = []
        self.quotes = []
        self.liveness = []
        self.following = None
        self.ids = {}

    async def resolve(self):
        for name, identifiers in ASKED.items():
            if name not in self.ids:
                description, currency = STATED.get(name, ("", ""))
                found = await self.plugin.resolve_identifier(
                    identifiers=identifiers,
                    stated_description=description,
                    stated_currency=currency,
                )
                if not found.instrument_id:
                    raise RuntimeError(f"{name} did not resolve: {found}")
                self.ids[name] = found.instrument_id
        return dict(self.ids)

    async def on_price(self, heard):
        self.heard.append(price_json(heard.message.price))

    async def on_trade(self, heard):
        self.trades.append(trade_json(heard.message.trade, getattr(heard, "caught_up", False)))

    async def on_quote(self, heard):
        self.quotes.append(quote_json(heard.message.quote))

    async def on_liveness(self, heard):
        self.liveness.append(liveness_json(heard.message.liveness))

    async def answer(self, path, query):
        one = lambda name: query.get(name, [""])[0]  # noqa: E731
        if path == "/resolve":
            return await self.resolve()
        if path == "/follow":
            if self.following is None:
                self.following = asyncio.ensure_future(
                    self.plugin.receive(prices_recorded=self.on_price, trades_recorded=self.on_trade,
                                        quotes_recorded=self.on_quote,
                                        liveness_recorded=self.on_liveness, subjects=query["subject"]))
            return {"following": query["subject"]}
        if path == "/heard":
            return {"heard": self.heard, "trades": self.trades, "quotes": self.quotes,
                    "liveness": self.liveness}
        if path == "/datasets":
            answer = await self.plugin.list_datasets()
            return {"datasets": [{"dataset": d.dataset, "declared_delay_ns": d.declared_delay_ns,
                                  "liveness": [liveness_json(item) for item in d.liveness]}
                                 for d in answer.datasets]}
        if path == "/trades":
            asked = {"subjects": [meridian.SubjectRef(entity_id=s) for s in query["subject"]]}
            if query.get("after"):
                partitions = [ops.PartitionSequence(partition=p.rsplit(":", 1)[0],
                                                     sequence=int(p.rsplit(":", 1)[1]))
                              for p in query["after"]]
                asked["after_watermark"] = ops.Watermark(partitions=partitions)
            else:
                asked["valid_from_ns"], asked["valid_until_ns"] = int(one("from")), int(one("until"))
            rows, cursor, watermark, unanswered = [], "", None, []
            while True:
                answer = await self.plugin.list_trades(**asked, page_size=500, cursor=cursor)
                rows += [trade_json(t) for t in answer.trades]
                watermark = watermark_json(answer.watermark)
                unanswered += [{"subject": u.subject.entity_id, "dataset": u.dataset,
                                "reason": ops.UnansweredReason.Name(u.reason)}
                               for u in answer.unanswered]
                cursor = answer.next_cursor
                if not cursor:
                    break
            return {"trades": rows, "watermark": watermark, "unanswered": unanswered}
        if path == "/quotes":
            answer = await self.plugin.list_quotes(
                subjects=[meridian.SubjectRef(entity_id=s) for s in query["subject"]])
            return {"quotes": [quote_json(q) for q in answer.quotes],
                    "unanswered": [{"subject": u.subject.entity_id, "dataset": u.dataset,
                                    "reason": ops.UnansweredReason.Name(u.reason)}
                                   for u in answer.unanswered]}
        if path == "/prices":
            asked = {"subjects": [meridian.SubjectRef(entity_id=s) for s in query["subject"]]}
            if one("dataset"):
                asked["sources"] = SourceChoice(named=[one("dataset")])
            if one("kind"):
                asked["kinds"] = [one("kind")]
            if one("date"):
                asked["business_date"] = one("date")
            answer = await self.plugin.list_prices(**asked)
            return {
                "prices": [price_json(p) for p in answer.prices],
                "unanswered": [{"subject": u.subject.entity_id, "dataset": u.dataset,
                                "reason": ops.UnansweredReason.Name(u.reason)}
                               for u in answer.unanswered],
            }
        return {"page": "the e2e's reader"}


def serve(reader):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            asked = reader.answer(parsed.path, urllib.parse.parse_qs(parsed.query))
            future = asyncio.run_coroutine_threadsafe(asked, LOOP)
            try:
                body, status = json.dumps(future.result(timeout=60), sort_keys=True), 200
            except Exception as failed:  # said on the page, for the run to quote
                body, status = json.dumps({"failed": f"{type(failed).__name__}: {failed}"}), 500
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args):
            pass

    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


#: What the stand-in registers, its whole declaration (contract v25): the
#: e2e prints it with meridian-declaration and the harness holds the
#: stand-in's registration to it.
DECLARATION = meridian.Declaration(
    interface=Interface(
        PORT,
        "The e2e's reader",
        pages=[Page("/", "Prices", levels=["read"], roles=["reporting"])],
    )
)


async def main():
    plugin = await meridian.connect(
        # Contract v25: what the stand-in registers is its declaration.
        declaration=DECLARATION
    )
    reader = Reader(plugin)
    threading.Thread(target=serve, args=(reader,), daemon=True).start()
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.set_event_loop(LOOP)
    LOOP.run_until_complete(main())
