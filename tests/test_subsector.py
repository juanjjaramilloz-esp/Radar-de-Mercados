"""Tests del lector del Observatorio de subsectores.

Casos calculados a mano sobre tablas mínimas: un HS4 repartido entre dos
grupos CIIU (como el café sin tostar, entre cultivo y trilla), la serie de un
subsector y el ranking de socios de un año.
"""

import pandas as pd

from tradefit.domain.subsector import (
    groups_for_product,
    latest_full_year,
    partners_for_group,
    series_for_group,
)

HS4_MAP = pd.DataFrame(
    {
        "hs4": ["0901", "0901", "2222"],
        "ciiu4_grupo": ["106", "012", "222"],
        "orden": [1, 2, 1],
        "participacion": [0.998, 0.002, 1.0],
    }
)

INDICADORES = pd.DataFrame(
    {
        "anio": [2025, 2024, 2026, 2024],
        "ciiu4_grupo": ["106", "106", "106", "222"],
        "gl_partida_socio": [0.21, 0.19, 0.11, 0.15],
    }
)

SOCIOS = pd.DataFrame(
    {
        "anio": [2024, 2024, 2024, 2023],
        "ciiu4_grupo": ["106", "106", "106", "106"],
        "pais": ["USA", "DEU", "BRA", "JPN"],
        "total": [30.0, 20.0, 10.0, 99.0],
    }
)


def test_grupos_de_un_producto_ordenados_por_peso():
    grupos = groups_for_product(HS4_MAP, "0901")
    assert list(grupos.ciiu4_grupo) == ["106", "012"]
    assert grupos.participacion.iloc[0] == 0.998


def test_producto_de_diez_digitos_se_recorta_a_hs4():
    assert list(groups_for_product(HS4_MAP, "0901110000").ciiu4_grupo) == ["106", "012"]


def test_umbral_descarta_los_grupos_marginales():
    grupos = groups_for_product(HS4_MAP, "0901", min_share=0.01)
    assert list(grupos.ciiu4_grupo) == ["106"]


def test_producto_sin_correspondencia_devuelve_tabla_vacia():
    assert groups_for_product(HS4_MAP, "9999").empty


def test_serie_del_subsector_en_orden_cronologico():
    serie = series_for_group(INDICADORES, "106")
    assert list(serie.anio) == [2024, 2025, 2026]


def test_socios_del_ano_pedido_por_comercio_total():
    socios = partners_for_group(SOCIOS, "106", 2024, top=2)
    assert list(socios.pais) == ["USA", "DEU"]  # 2023 no entra aunque sea mayor


def test_ultimo_ano_completo_ignora_el_parcial():
    assert latest_full_year(INDICADORES, partial_years={2026}) == 2025
    assert latest_full_year(INDICADORES, partial_years={2024, 2025, 2026}) is None


def test_los_archivos_versionados_cumplen_lo_que_la_app_espera():
    """Contrato de los artefactos del Observatorio que viajan en el repo."""
    from tradefit import config

    esperado = {
        config.hs4_subsector_parquet(): {"hs4", "ciiu4_grupo", "participacion"},
        config.subsector_indicadores_parquet(): {"anio", "ciiu4_grupo", "X", "M", "balanza",
                                                 "gl_partida", "gl_partida_socio"},
        config.subsector_socios_parquet(): {"anio", "ciiu4_grupo", "pais", "total",
                                            "gl_partida", "cuota_x", "cuota_m"},
        config.subsector_partidas_parquet(): {"ciiu4_grupo", "partida", "descripcion", "total"},
    }
    for ruta, columnas in esperado.items():
        assert ruta.exists(), f"falta {ruta.name}"
        tabla = pd.read_parquet(ruta)
        faltan = columnas - set(tabla.columns)
        assert not faltan, f"{ruta.name}: faltan {faltan}"

    indicadores = pd.read_parquet(config.subsector_indicadores_parquet())
    gl = indicadores["gl_partida_socio"].dropna()
    assert gl.between(0, 1).all()  # el índice es una fracción, no un porcentaje
