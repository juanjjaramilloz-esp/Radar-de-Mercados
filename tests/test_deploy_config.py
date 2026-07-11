"""Regresiones de seguridad de la configuración de despliegue."""

import tomllib
from pathlib import Path


def test_streamlit_mantiene_cors_y_xsrf_activos() -> None:
    """El despliegue público no debe desactivar las protecciones web."""
    path = Path(__file__).parents[1] / ".streamlit" / "config.toml"
    config = tomllib.loads(path.read_text(encoding="utf-8"))

    assert config["server"]["enableCORS"] is True
    assert config["server"]["enableXsrfProtection"] is True
