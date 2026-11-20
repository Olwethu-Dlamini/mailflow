#!/usr/bin/env bash
# Build both MailFlow decks (PPTX) and their PDFs.
# Needs: uv (for python-pptx and Pillow) and LibreOffice (soffice) for the PDFs.
# Screens come from docs/images/app/, made with deck/demo_server.py (made-up emails only).
set -euo pipefail
cd "$(dirname "$0")"
uv run --no-project --with python-pptx python build_client.py
uv run --no-project --with python-pptx python build_technical.py
soffice --headless --convert-to pdf --outdir . MailFlow-Client.pptx MailFlow-Technical.pptx >/dev/null
ls -la MailFlow-*.pdf
