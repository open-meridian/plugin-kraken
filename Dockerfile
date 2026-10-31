# The plugin's image. It runs beside a sidecar in the deployment's cluster, and
# reaches nothing but that sidecar and Kraken's public REST.
#
# Built on the base image for the SDK this plugin pins: Python and
# open-meridian, the same version as pyproject.toml's, already installed. So
# the image's own layer is this plugin, and an upload sends only that. Move the
# two together when moving to a new SDK.
#
# BASE is for building against a base made locally rather than a released one:
# `make image` builds plugin-python:<version>-local from the sibling
# meridian-python while that version is not published.
# The release by its tag and its digest, the image exactly; move both together.
ARG BASE=ghcr.io/open-meridian/plugin-python:0.33.4@sha256:73937d83e947c7a8d2618af7fc846364b96ed85d83314921ae21e51ac4ee95c6
FROM ${BASE}
WORKDIR /plugin
# Installed from a mount rather than copied, so the image holds the installed
# package and no source beside it.
RUN --mount=type=bind,target=/tmp/src,rw pip install --no-cache-dir /tmp/src
# The vendor's documentation (contract v25): the declaration names docs/,
# relative to where the plugin runs, /plugin, and `meridian-declaration`
# reads it there when `meridian plugin upload` prints the declaration.
COPY docs/ docs/
USER 65532
CMD ["kraken"]
