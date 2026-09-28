"""Página de la ficha de operación: textos completos y render con los datos versionados."""

import re
from pathlib import Path

from streamlit.testing.v1 import AppTest

from tradefit.app import i18n

RAIZ = Path(__file__).parents[1]
FICHA = RAIZ / "src" / "tradefit" / "app" / "ficha.py"


def test_cada_texto_de_la_ficha_existe_en_los_dos_idiomas() -> None:
    fuente = FICHA.read_text(encoding="utf-8")
    claves = set(re.findall(r'\bt\(\s*"([a-z0-9_]+)"', fuente))
    claves |= {m for m in re.findall(r'\(\s*"(ficha_doc_[a-z_]+)"', fuente)}
    claves |= {f"ficha_price_{p}" for p in ("debajo", "dentro", "encima")}
    faltan = sorted(c for c in claves if c not in i18n._STRINGS)
    assert not faltan, faltan
    for clave in claves:
        assert set(i18n._STRINGS[clave]) == {"es", "en"}, clave


def _render(query: dict[str, str]) -> AppTest:
    def app() -> None:
        import sys  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        sys.path.insert(0, str(Path.cwd() / "src"))
        from tradefit.app.ficha import page  # noqa: PLC0415

        page()

    at = AppTest.from_function(app, default_timeout=60)
    for k, v in query.items():
        at.query_params[k] = v
    return at.run()


def test_la_ficha_se_renderiza_con_los_datos_versionados() -> None:
    at = _render({"hs": "3808", "hs6": "380892", "pais": "ECU"})
    assert not at.exception, at.exception
    textos = " ".join(m.value for m in at.markdown)
    assert "Ecuador" in textos
    # Sin precio pactado, la ficha pide uno en vez de inventar la comparación.
    assert "Escriba un precio pactado" in textos


def test_con_precio_pactado_dice_donde_cae() -> None:
    at = _render({"hs": "3808", "hs6": "380892", "pais": "ECU"})
    at.number_input[1].set_value(11.4).run()
    assert not at.exception, at.exception
    textos = " ".join(m.value for m in at.markdown)
    assert "rango habitual" in textos


def test_todo_socio_del_observatorio_tiene_nombre_y_bandera() -> None:
    import pandas as pd  # noqa: PLC0415

    from tradefit import config  # noqa: PLC0415
    from tradefit.app import paises  # noqa: PLC0415

    anual = pd.read_parquet(config.ficha_anual_parquet())
    socios = pd.read_parquet(config.subsector_socios_parquet())
    faltan = sorted((set(anual["pais"]) | set(socios["pais"])) - set(paises.PAISES))
    assert not faltan, faltan
    assert all(len(iso2) == 2 for iso2, _, _ in paises.PAISES.values())
