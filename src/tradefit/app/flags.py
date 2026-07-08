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
    # Destinos LATAM (2026-07-08)
    "MEX": "MX",
    "BRA": "BR",
    "CHL": "CL",
    "PER": "PE",
    "ECU": "EC",
    "CRI": "CR",
    "PAN": "PA",
    "DOM": "DO",
}

#: Color característico de la bandera de cada país (hex), para identificar
#: mercados en las gráficas y chips del comparador. Curado a mano: se toma
#: un tono representativo del pabellón, prefiriendo el que mejor lo
#: distingue de los demás destinos (varias banderas comparten familia
#: cromática — con máx. 3 mercados a la vez la colisión es tolerable).
FLAG_COLORS: Final[dict[str, str]] = {
    "USA": "#3C3B6E",  # azul marino del cantón
    "DEU": "#FFCC00",  # oro
    "ITA": "#008C45",  # verde
    "FRA": "#0055A4",  # azul
    "JPN": "#BC002D",  # rojo del disco
    "CAN": "#D80621",  # rojo hoja de arce
    "BEL": "#2D2926",  # negro
    "NLD": "#FF6F00",  # naranja (color nacional)
    "ESP": "#AA151B",  # rojo
    "GBR": "#012169",  # azul Union Jack
    "KOR": "#0047A0",  # azul del taegeuk
    "CHE": "#DA291C",  # rojo
    "POL": "#DC143C",  # carmesí
    "SWE": "#FECC02",  # amarillo de la cruz
    "AUS": "#003087",  # azul marino
    "PRT": "#046A38",  # verde
    "FIN": "#002F6C",  # azul de la cruz
    "AUT": "#EF3340",  # rojo
    "MEX": "#006341",  # verde
    "BRA": "#009739",  # verde
    "CHL": "#0032A0",  # azul del cantón
    "PER": "#D91023",  # rojo
    "ECU": "#FFD100",  # amarillo
    "CRI": "#CE1126",  # rojo
    "PAN": "#005293",  # azul
    "DOM": "#002D62",  # azul marino
    "COL": "#FCD116",  # amarillo (origen)
}

#: Fallback para un ISO3 sin color curado (partida rara del buscador).
_DEFAULT_FLAG_COLOR: Final = "#1D4ED8"

_REGIONAL_INDICATOR_OFFSET: Final = 0x1F1E6 - ord("A")


def flag_color(iso3: str) -> str:
    """Color hex característico de la bandera de ``iso3``.

    Args:
        iso3: código ISO 3166-1 alpha-3 (insensible a mayúsculas).

    Returns:
        Hex ``#RRGGBB`` de :data:`FLAG_COLORS`, o un azul neutro si el país
        no está curado.
    """
    return FLAG_COLORS.get(iso3.upper(), _DEFAULT_FLAG_COLOR)


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
