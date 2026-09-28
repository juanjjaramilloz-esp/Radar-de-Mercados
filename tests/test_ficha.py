"""Ficha de operación: precio de referencia, proveedores, arancel y umbral de confidencialidad."""

import pandas as pd
import pytest

from tradefit.domain import ficha

ANUAL = pd.DataFrame(
    {
        "flujo": ["X", "X", "X", "X", "X", "M", "M", "M"],
        "anio": [2025, 2024, 2025, 2025, 2025, 2025, 2025, 2025],
        "hs6": ["380892"] * 8,
        "pais": ["ECU", "ECU", "PER", "BRA", "GTM", "CHN", "USA", "IND"],
        "valor": [1200.0, 900.0, 800.0, 300.0, 50.0, 600.0, 300.0, 100.0],
        "kg": [100.0, 100.0, 40.0, 50.0, 5.0, 120.0, 10.0, 25.0],
        "registros": [20, 15, 9, 2, 3, 30, 8, 1],
    }
)
MENSUAL = pd.DataFrame(
    {
        "anio": [2025] * 5 + [2024],
        "mes": [1, 2, 3, 4, 5, 1],
        "hs6": ["380892"] * 6,
        "pais": ["ECU"] * 6,
        "valor_unitario": [10.0, 12.0, 14.0, 16.0, 30.0, 9.0],
        "registros": [4, 3, 5, 6, 3, 4],
    }
)


def test_valor_unitario_respeta_el_umbral():
    assert ficha.valor_unitario(100.0, 10.0, 3) == pytest.approx(10.0)
    assert ficha.valor_unitario(100.0, 10.0, 2) is None  # precio de una o dos empresas
    assert ficha.valor_unitario(100.0, 0.0, 9) is None  # sin peso no hay valor unitario


def test_precio_referencia_a_mano():
    p = ficha.precio_referencia(ANUAL, MENSUAL, "380892", "ECU", 2025)
    assert list(p.meses["mes"]) == [1, 2, 3, 4, 5]
    # Percentiles lineales de 10, 12, 14, 16, 30.
    assert p.p25 == pytest.approx(12.0)
    assert p.mediana == pytest.approx(14.0)
    assert p.p75 == pytest.approx(16.0)
    # El promedio del año es valor total / kg total, no el promedio de los meses.
    assert p.promedio == pytest.approx(12.0)
    assert p.registros == 20
    assert p.serie.set_index("anio")["valor_unitario"].to_dict() == {2024: 9.0, 2025: 12.0}


def test_otros_destinos_ocultan_el_precio_con_pocos_registros():
    p = ficha.precio_referencia(ANUAL, MENSUAL, "380892", "ECU", 2025)
    o = p.otros_destinos.set_index("pais")
    assert list(o.index) == ["PER", "BRA", "GTM"]  # por valor, sin el destino elegido
    assert o.loc["PER", "valor_unitario"] == pytest.approx(20.0)
    assert pd.isna(o.loc["BRA", "valor_unitario"])  # 2 registros: no se publica
    assert o.loc["GTM", "valor_unitario"] == pytest.approx(10.0)


def test_sin_meses_suficientes_no_hay_rango():
    pocos = MENSUAL[MENSUAL["mes"] <= 3]
    p = ficha.precio_referencia(ANUAL, pocos, "380892", "ECU", 2025)
    assert p.p25 is None and p.p75 is None
    assert ficha.posicion_precio(11.0, p.p25, p.p75) is None


def test_posicion_del_precio_pactado():
    assert ficha.posicion_precio(11.0, 12.0, 16.0) == "debajo"
    assert ficha.posicion_precio(12.0, 12.0, 16.0) == "dentro"
    assert ficha.posicion_precio(16.5, 12.0, 16.0) == "encima"
    assert ficha.posicion_precio(0.0, 12.0, 16.0) is None


def test_proveedores_de_colombia_con_hhi_sobre_todos():
    p = ficha.proveedores_colombia(ANUAL, "380892", 2025, top=2)
    assert p.total == pytest.approx(1000.0)
    assert list(p.tabla["pais"]) == ["CHN", "USA"]
    assert p.tabla["cuota"].tolist() == pytest.approx([0.6, 0.3])
    # HHI con los tres orígenes, aunque solo se muestren dos.
    assert p.hhi == pytest.approx(0.6**2 + 0.3**2 + 0.1**2)
    assert p.tabla.set_index("pais").loc["USA", "valor_unitario"] == pytest.approx(30.0)


def test_proveedores_del_destino_siempre_muestran_a_colombia():
    comp = pd.DataFrame(
        {
            "country_iso3": ["ECU"] * 4 + ["ECU"],
            "partner_code": ["156", "842", "699", "170", "156"],
            "partner_name": ["China", "USA", "India", "Colombia", "China"],
            "year": [2024, 2024, 2024, 2024, 2023],
            "value_usd": [50.0, 30.0, 15.0, 5.0, 40.0],
            "supplier_share": [0.5, 0.3, 0.15, 0.05, 0.6],
            "supplier_rank": [1, 2, 3, 4, 1],
        }
    )
    p = ficha.proveedores_destino(comp, "ECU", top=2)
    assert list(p["partner_name"]) == ["China", "USA", "Colombia"]
    assert p["es_colombia"].tolist() == [False, False, True]
    assert set(p["year"]) == {2024}


def test_arancel_prefiere_el_preferencial_mas_reciente():
    perfil = pd.DataFrame(
        {
            "country_iso3": ["ECU", "ECU", "ECU", "PER"],
            "cmd_code": ["380892", "380892", "380892", "380892"],
            "tariff_type": ["MFN", "PREF", "PREF", "MFN"],
            "year": [2023, 2019, 2021, 2023],
            "tariff_faced": [0.05, 0.02, 0.0165, 0.06],
        }
    )
    ecu = ficha.arancel_subpartida(perfil, "ECU", "380892")
    assert ecu is not None
    assert (ecu.arancel, ecu.tipo, ecu.anio) == (pytest.approx(0.0165), "PREF", 2021)
    per = ficha.arancel_subpartida(perfil, "PER", "380892")
    assert per is not None and per.tipo == "MFN"
    assert ficha.arancel_subpartida(perfil, "BRA", "380892") is None


def test_subpartidas_exportadas_ordenadas_por_valor():
    s = ficha.subpartidas_exportadas(ANUAL, "3808", 2025)
    assert list(s["hs6"]) == ["380892"]
    assert s["valor"].iloc[0] == pytest.approx(2350.0)


def test_destino_fuera_de_los_principales_socios_no_es_cero():
    socios = pd.DataFrame(
        {
            "anio": [2025],
            "ciiu4_grupo": ["202"],
            "pais": ["ECU"],
            "X": [333.9],
            "M": [14.5],
            "total": [348.4],
            "gl_partida": [0.058],
            "cuota_x": [0.165],
            "cuota_m": [0.004],
        }
    )
    assert ficha.destino_en_subsector(socios, "202", "ECU", 2025)["cuota_x"] == pytest.approx(0.165)
    assert ficha.destino_en_subsector(socios, "202", "JPN", 2025) is None
