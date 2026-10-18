"""What this version declares beside its roles (W8.1, W4.1): from contract
v25 the whole of what it says about itself.

Built from the plugin's code and used twice: `__main__` registers with it,
and `meridian plugin upload` reads the same one from the built image
(pyproject.toml's `[tool.meridian] declaration`), with the documentation's
texts beside it. A version registers exactly the declaration it was uploaded
with, or its sidecar refuses it naming the first difference, so beside the
parts it declared before (declared.py, whose docstring says what each is)
it carries its interface -- its pages, with the levels each serves, and the
tools their typed routes make -- on a port fixed here, never read from the
environment, and the vendor's documentation, the Markdown in `docs/`
(`/plugin/docs` in its image), which a deployment admin reads on its
Documentation tab before launching it.
"""

from __future__ import annotations

import meridian
from meridian import Declaration, RecordKind, Storage

from .declared import CATALOGUE, KIND, LABEL, SETTINGS, WINDOW_DAYS
from .page import TITLE, pages

#: The port its pages are served on, on loopback, where its sidecar forwards.
PORT = 8000

DECLARATION = Declaration(
    settings=SETTINGS,
    storage=Storage(kinds=[RecordKind(KIND, LABEL, window_days=WINDOW_DAYS)]),
    catalogue=CATALOGUE,
    interface=meridian.Interface(port=PORT, title=TITLE, pages=pages),
    documentation="docs",
)
