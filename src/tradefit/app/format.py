"""Formato numérico y posiciones relativas (presentación pura, sin Streamlit).

Convención española: «.» para miles y «,» para decimales (RAE, *Ortografía*,
§ apéndice de números); la inglesa es la inversa. Funciones puras y
determinísticas para que ``app/export.py`` (que no depende de Streamlit) y
los tests las usen pasando el idioma explícito; ``app/i18n.py`` expone
wrappers que leen el idioma activo de la sesión.
"""

from math import ceil
from typing import Final, Literal

Lang = Literal["es", "en"]

#: Intercambia separadores ingleses ↔ españoles ("1,234.5" → "1.234,5").
_SWAP_TO_ES: Final = str.maketrans({",": ".", ".": ","})


def format_number(value: float, decimals: int = 0, lang: Lang = "es", signed: bool = False) -> str:
    """Número con separador de miles y decimales según el idioma.

    Args:
        value: valor a formatear.
        decimals: cifras decimales fijas.
        lang: ``"es"`` → ``1.234,5``; ``"en"`` → ``1,234.5``.
        signed: antepone ``+`` a los valores positivos.

    Returns:
        El número formateado, p. ej. ``format_number(1234.5, 1) == "1.234,5"``.
    """
    sign = "+" if signed else "-"
    text = f"{value:{sign},.{decimals}f}"
    return text.translate(_SWAP_TO_ES) if lang == "es" else text


def format_pct(fraction: float, decimals: int = 1, lang: Lang = "es", signed: bool = False) -> str:
    """Fracción como porcentaje: ``0.202 → "20,2 %"`` (es) / ``"20.2 %"`` (en).

    Args:
        fraction: fracción (0.202 = 20.2 %).
        decimals: cifras decimales fijas.
        lang: idioma de los separadores.
        signed: antepone ``+`` a los valores positivos.

    Returns:
        El porcentaje formateado, con espacio fino antes del símbolo.
    """
    return f"{format_number(fraction * 100, decimals, lang, signed)} %"


def plotly_separators(lang: Lang) -> str:
    """Cadena ``separators`` de Plotly (decimal + miles) para el idioma dado."""
    return ",." if lang == "es" else ".,"


def top_share_percent(rank: int, population: int) -> int:
    """Convierte un puesto en el porcentaje superior que ocupa en su universo.

    Args:
        rank: posición ordinal, empezando en 1.
        population: número total de alternativas rankeadas.

    Returns:
        Porcentaje entero redondeado hacia arriba. Por ejemplo, el puesto 1
        entre 20 mercados pertenece al ``top 5 %``.

    Raises:
        ValueError: si la posición o el tamaño del universo no son válidos.
    """
    if population < 1:
        raise ValueError("population must be positive")
    if rank < 1 or rank > population:
        raise ValueError("rank must be between 1 and population")
    return ceil(rank / population * 100)
