"""Tests del formato numérico por idioma (app/format.py).

Valores calculados a mano: la convención española usa «.» para miles y «,»
para decimales; la inglesa, la inversa.
"""

import pytest

from tradefit.app.format import format_number, format_pct, plotly_separators, top_share_percent


def test_format_number_es_miles_y_decimales() -> None:
    assert format_number(1234.5, 1, "es") == "1.234,5"
    assert format_number(171_000_000 / 1e6, 0, "es") == "171"
    assert format_number(1_234_567.891, 2, "es") == "1.234.567,89"


def test_format_number_en_convencion_inglesa() -> None:
    assert format_number(1234.5, 1, "en") == "1,234.5"
    assert format_number(1_234_567.891, 2, "en") == "1,234,567.89"


def test_format_number_signed_antepone_mas() -> None:
    assert format_number(0.5, 1, "es", signed=True) == "+0,5"
    assert format_number(-0.5, 1, "es", signed=True) == "-0,5"


def test_format_pct_es_y_en() -> None:
    assert format_pct(0.202, 1, "es") == "20,2 %"
    assert format_pct(0.202, 1, "en") == "20.2 %"
    assert format_pct(0.428, 1, "es") == "42,8 %"


def test_format_pct_signed() -> None:
    assert format_pct(0.077, 1, "es", signed=True) == "+7,7 %"


def test_plotly_separators() -> None:
    # Plotly espera "<decimal><miles>": español = coma decimal, punto de miles.
    assert plotly_separators("es") == ",."
    assert plotly_separators("en") == ".,"


@pytest.mark.parametrize(
    ("rank", "population", "expected"),
    [(1, 20, 5), (1, 3, 34), (5, 100, 5), (1, 500, 1), (7, 7, 100)],
)
def test_top_share_percent(rank: int, population: int, expected: int) -> None:
    assert top_share_percent(rank, population) == expected


@pytest.mark.parametrize(("rank", "population"), [(0, 10), (11, 10), (1, 0)])
def test_top_share_percent_rechaza_posiciones_invalidas(rank: int, population: int) -> None:
    with pytest.raises(ValueError):
        top_share_percent(rank, population)
