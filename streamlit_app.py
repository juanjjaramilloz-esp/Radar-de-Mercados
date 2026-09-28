"""Entry point para Streamlit Community Cloud.

El cloud ejecuta este archivo desde la raíz del repo; solo agrega ``src/`` al
path e invoca la navegación de la app (``tradefit.app.navegacion``): el Radar
de mercados y la ficha de operación. La app lee el snapshot versionado de
``data/processed/`` — nunca llama APIs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from tradefit.app.navegacion import ejecutar  # noqa: E402

ejecutar()
