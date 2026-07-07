"""Banderas emoji por código ISO3 (presentación pura, sin I/O ni red)."""

from typing import Final

# ISO 3166-1 alpha-3 → alpha-2 de los países que usa la app (destinos del
# MVP + origen). Un país fuera del mapeo simplemente no lleva bandera.
_ISO3_TO_ISO2: Final[dict[str, str]] = {
    "AUS": "AU",
    "AUT": "AT",
    "BEL": "BE",
    "CAN": "CA",
    "CHE": "CH",
    "COL": "CO",
    "DEU": "DE",
    "ESP": "ES",
    "FIN": "FI",
    "FRA": "FR",
    "GBR": "GB",
    "ITA": "IT",
    "JPN": "JP",
    "KOR": "KR",
    "NLD": "NL",
    "POL": "PL",
    "PRT": "PT",
    "SWE": "SE",
    "USA": "US",
}

_REGIONAL_INDICATOR_OFFSET: Final = 0x1F1E6 - ord("A")


def flag_emoji(iso3: str) -> str:
    """Bandera emoji del país ``iso3``, o cadena vacía si no está mapeado.

    Unicode compone una bandera con dos *regional indicator symbols*, uno por
    letra del código ISO 3166-1 alpha-2 (p. ej. ``US`` → 🇺🇸).

    Args:
        iso3: código ISO 3166-1 alpha-3 (insensible a mayúsculas).

    Returns:
        La bandera emoji, o ``""`` si el país no está en el mapeo local.
    """
    iso2 = _ISO3_TO_ISO2.get(iso3.upper())
    if iso2 is None:
        return ""
    return "".join(chr(_REGIONAL_INDICATOR_OFFSET + ord(char)) for char in iso2)
