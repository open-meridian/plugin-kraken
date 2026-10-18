"""What this version declares beside its role (W8.1, W4.1; contracts v18 and v19).

**Its catalogue** (spec/the-lake, "The catalogue"; the plan's Q5 and Q21),
declared from code and read the same way at registration and by `meridian
plugin upload`:

- `daily`: each product's close and bar for a UTC day, its day ending at
  00:00 UTC (`day_time_zone` `Etc/UTC`, `day_end_minute` 0, as the plan
  rules for a venue with no official close), pulled for what the lake
  wants and pushed for a standing want; kept.
- `live`: the last trade's price and the best bid and offer as prices, at
  most once a second per subject and kind, pulled for the latest or kept
  current for a standing want; and from contract v19 the best bid and offer
  with their sizes as a quote, kept current from the venue's stream while a
  standing want stands; kept two days.
- `trades` (contract v19): every trade, from the venue's stream for the
  subjects under a standing want, or from its REST history for a range
  wanted; declared apart from the live prices, so an admin licenses and
  keeps them apart (the plan's Q40), kept two days.

Each licence is what Kraken's standard terms say, which the deployment's
licence confirms or replaces, never whether a deployment meets them: Kraken
asks its prior permission for "any non-personal commercial use of data from
publicly accessible endpoints", so its data is one person's without that
permission, kept for that person's own use (README, "Kraken's terms"; not
legal advice). `daily` reaches back 720 days, the most `OHLC` gives.

`venue_id` is empty: the venue master's ID for Kraken (which has no MIC) is minted by
the platform, not known to the code a catalogue is declared from, so each row
names the venue by the ID it resolves at run time (the SDK's
`meridian.roles.data.pairs.Feed`), and the
catalogue names none (README, "The venue").

**Its storage**: one kind of raw record, Kraken's responses as received,
kept a month by default (`KIND`, kept by the SDK's
`meridian.edge.RawStore`); the SDK declares the kind's two window settings.
**Its settings**: sample data, a developer's (synthetic.py). No secret:
Kraken's public market data needs no key.
"""

import meridian
from meridian import DatasetDeclaration, DatasetLicence

VENDOR = "Kraken"
SAMPLE_DATA = "sample_data"

#: Its one kind of raw record, Kraken's responses as received: a month of
#: them by default, enough to re-convert a row a person questions. An admin
#: sets the window in Settings.
KIND = "responses"
LABEL = "Raw responses"
WINDOW_DAYS = 30

#: Its settings, in the data role's order (spec/plugin-pages-follow-their-role):
#: no environment and no credential -- Kraken's public market data has one
#: environment and needs no key -- so only sample data, a developer's.
SETTINGS = [
    meridian.sample_data(
        description=(
            "Answer from built-in made-up Kraken responses, or a developer's recorded ones, "
            "instead of calling Kraken. Development deployments only."
        )
    ),
]

CATALOGUE = [
    DatasetDeclaration(
        key="daily",
        vendor=VENDOR,
        data_types=[
            "meridian.v1.Price",
            "meridian.v1.Bar",
            "meridian.v1.Bar.vwap",
            "meridian.v1.Bar.trade_count",
        ],
        modes=["pull", "push"],
        cadence=86_400,
        history=720,
        licence_default=DatasetLicence(
            kept=True, derived_use=True, display=True, personal_use=True
        ),
        day_time_zone="Etc/UTC",
        day_end_minute=0,
    ),
    DatasetDeclaration(
        key="live",
        vendor=VENDOR,
        data_types=["meridian.v1.Price", "meridian.v1.Quote"],
        modes=["pull", "stream"],
        cadence=1,
        history=0,
        licence_default=DatasetLicence(
            kept=True, retention_days=2, display=True, personal_use=True
        ),
        day_time_zone="Etc/UTC",
        day_end_minute=0,
    ),
    DatasetDeclaration(
        key="trades",
        vendor=VENDOR,
        data_types=["meridian.v1.Trade"],
        modes=["pull", "stream"],
        cadence=1,
        history=0,
        licence_default=DatasetLicence(
            kept=True, retention_days=2, display=True, personal_use=True
        ),
        day_time_zone="Etc/UTC",
        day_end_minute=0,
    ),
]
