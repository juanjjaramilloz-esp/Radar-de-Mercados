"""Tests del filtro macro con valores calculados a mano.

El caso central que exige el PLAN: un país estable y uno inestable con el
mismo score de oportunidad — el orden esperado tras la penalización es obvio.
"""

import pandas as pd
import pytest

from tradefit import config
from tradefit.domain.macro_filter import (
    NEUTRAL_STABILITY,
    apply_stability_penalty,
    latest_indicator_value,
    stability_score,
)

BOUNDS = {
    "inflation": (15.0, 2.0),
    "gdp_growth": (-2.0, 3.0),
    "current_account": (-5.0, 0.0),
}


def _macro(rows: list[tuple[str, str, int, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=[
            config.COL_COUNTRY,
            config.COL_INDICATOR,
            config.COL_YEAR,
            config.COL_MACRO_VALUE,
        ],
    )


def test_estabilidad_extremos_a_mano() -> None:
    macro = _macro(
        [
            # STA en el mejor umbral de los 3 indicadores → 1.0
            ("STA", "inflation", 2024, 2.0),
            ("STA", "gdp_growth", 2024, 3.0),
            ("STA", "current_account", 2024, 0.0),
            # UNS en el peor umbral de los 3 → 0.0
            ("UNS", "inflation", 2024, 15.0),
            ("UNS", "gdp_growth", 2024, -2.0),
            ("UNS", "current_account", 2024, -5.0),
        ]
    )
    stability = stability_score(macro, BOUNDS)
    assert stability["STA"] == pytest.approx(1.0)
    assert stability["UNS"] == pytest.approx(0.0)


def test_estabilidad_punto_medio_a_mano() -> None:
    macro = _macro(
        [
            # Cada indicador exactamente a mitad de su rampa → 0.5
            ("MID", "inflation", 2024, 8.5),  # (8.5−15)/(2−15) = 0.5
            ("MID", "gdp_growth", 2024, 0.5),  # (0.5+2)/(3+2) = 0.5
            ("MID", "current_account", 2024, -2.5),  # (−2.5+5)/(0+5) = 0.5
        ]
    )
    assert stability_score(macro, BOUNDS)["MID"] == pytest.approx(0.5)


def test_estabilidad_recorta_fuera_de_rango() -> None:
    macro = _macro(
        [
            ("HIP", "inflation", 2024, 50.0),  # hiperinflación → 0, no negativo
            ("DEF", "inflation", 2024, 0.5),  # mejor que la meta → 1, no >1
        ]
    )
    stability = stability_score(macro, BOUNDS)
    assert stability["HIP"] == pytest.approx(0.0)
    assert stability["DEF"] == pytest.approx(1.0)


def test_estabilidad_promedia_la_ventana() -> None:
    macro = _macro(
        [
            # 2021 (fuera de la ventana de 3) no cuenta; (1+2+3)/3 = 2 → score 1.0
            ("AVG", "inflation", 2021, 99.0),
            ("AVG", "inflation", 2022, 1.0),
            ("AVG", "inflation", 2023, 2.0),
            ("AVG", "inflation", 2024, 3.0),
        ]
    )
    assert stability_score(macro, BOUNDS, years=3)["AVG"] == pytest.approx(1.0)


def test_indicador_faltante_promedia_los_presentes() -> None:
    macro = _macro([("ONE", "inflation", 2024, 2.0)])  # solo un indicador, en 1.0
    assert stability_score(macro, BOUNDS)["ONE"] == pytest.approx(1.0)


def test_indicador_sin_umbrales_falla() -> None:
    macro = _macro([("USA", "desempleo", 2024, 5.0)])
    with pytest.raises(ValueError, match="umbrales"):
        stability_score(macro, BOUNDS)


def test_ultimo_valor_por_pais_con_anios_esparsos() -> None:
    # LPI real-a-escala: DEU tiene 2018 y 2023 (gana 2023); NLD solo 2018.
    macro = _macro(
        [
            ("DEU", "lpi", 2018, 4.2),
            ("DEU", "lpi", 2023, 4.1),
            ("NLD", "lpi", 2018, 4.0),
            # Otro indicador del mismo caché: no debe colarse.
            ("DEU", "inflation", 2024, 2.0),
        ]
    )
    latest = latest_indicator_value(macro, "lpi")
    assert latest["DEU"] == pytest.approx(4.1)
    assert latest["NLD"] == pytest.approx(4.0)
    assert latest.name == "lpi"
    assert set(latest.index) == {"DEU", "NLD"}


def test_ultimo_valor_indicador_ausente_devuelve_vacio() -> None:
    macro = _macro([("USA", "inflation", 2024, 3.0)])
    assert latest_indicator_value(macro, "lpi").empty


def _toy_ranking() -> pd.DataFrame:
    return pd.DataFrame(
        {
            config.COL_RANK: [1, 2],
            config.COL_COUNTRY: ["AAA", "BBB"],
            config.COL_SCORE: [1.0, 0.9],
        }
    )


def test_penalizacion_invierte_el_orden_esperado() -> None:
    # AAA lidera en oportunidad pero es inestable; BBB es estable y lo pasa
    stability = pd.Series({"AAA": 0.0, "BBB": 1.0})
    result = apply_stability_penalty(_toy_ranking(), stability, floor=0.5).set_index(
        config.COL_COUNTRY
    )
    # AAA: 1.0 × (0.5 + 0.5×0) = 0.50; BBB: 0.9 × (0.5 + 0.5×1) = 0.90
    assert result.loc["AAA", config.COL_FINAL_SCORE] == pytest.approx(0.50)
    assert result.loc["BBB", config.COL_FINAL_SCORE] == pytest.approx(0.90)
    assert result.loc["BBB", config.COL_RANK] == 1  # BBB queda primero
    assert result.loc["AAA", config.COL_RANK] == 2


def test_pais_sin_estabilidad_recibe_neutra() -> None:
    stability = pd.Series({"AAA": 1.0})  # BBB sin dato
    result = apply_stability_penalty(_toy_ranking(), stability, floor=0.5).set_index(
        config.COL_COUNTRY
    )
    assert result.loc["BBB", config.COL_STABILITY] == pytest.approx(NEUTRAL_STABILITY)
    # BBB: 0.9 × (0.5 + 0.5×0.5) = 0.675
    assert result.loc["BBB", config.COL_FINAL_SCORE] == pytest.approx(0.675)


def test_floor_invalido_falla() -> None:
    with pytest.raises(ValueError, match="floor"):
        apply_stability_penalty(_toy_ranking(), pd.Series(dtype=float), floor=1.5)
