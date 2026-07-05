"""Entry point para Streamlit Community Cloud.

El cloud ejecuta este archivo desde la raíz del repo; solo agrega ``src/`` al
path e invoca la app real (``tradefit.app.main``). La app lee el snapshot
versionado de ejemplo en ``data/processed/`` — nunca llama APIs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from tradefit.app.main import main  # noqa: E402

main()
