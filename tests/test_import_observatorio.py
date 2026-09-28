"""Contrato Observatorio → Radar: hashes, versión del contrato y esquemas."""

from pathlib import Path

import pandas as pd
import pandera.errors
import pytest

from tradefit import config
from tradefit.pipeline.import_observatorio import import_package, verify_package
from tradefit.pipeline.snapshot_io import write_manifest

INDICADORES = pd.DataFrame(
    {
        "anio": [2024],
        "ciiu4_grupo": ["222"],
        "X": [2e6],
        "M": [1e6],
        "balanza": [1e6],
        "cobertura": [2.0],
        "saldo_normalizado": [1 / 3],
        "gl_partida_socio": [0.3],
        "gl_hs6_socio": [0.35],
        "gl_partida": [0.6],
        "gl_totales": [0.67],
        "hhi_socios_expo": [0.5],
        "hhi_socios_impo": [0.3],
        "x_socios_nacionales": [1e5],
        "m_socios_nacionales": [0.0],
        "partidas": [10],
        "grupo_nombre": ["Fabricación de productos de plástico"],
    }
)
SOCIOS = pd.DataFrame(
    {
        "anio": [2024],
        "ciiu4_grupo": ["222"],
        "pais": ["ECU"],
        "X": [1e6],
        "M": [1e5],
        "total": [1.1e6],
        "gl_partida": [0.1],
        "cuota_x": [0.5],
        "cuota_m": [0.1],
    }
)
HS4 = pd.DataFrame(
    {
        "hs4": ["3923", "0901", "0901"],
        "ciiu4_grupo": ["222", "106", "012"],
        "orden": [1, 1, 2],
        "participacion": [1.0, 0.9, 0.1],
        "X": [1e6, 9e6, 1e6],
        "M": [1e5, 0.0, 0.0],
    }
)
PARTIDAS = pd.DataFrame(
    {
        "ciiu4_grupo": ["222"],
        "partida": ["3923509000"],
        "X": [1e6],
        "M": [1e5],
        "total": [1.1e6],
        "descripcion": ["Tapones, tapas, cápsulas"],
    }
)
FICHA_ANUAL = pd.DataFrame(
    {
        "flujo": ["X", "M"],
        "anio": [2024, 2024],
        "hs6": ["392350", "392350"],
        "pais": ["ECU", "CHN"],
        "valor": [1e6, 2e5],
        "kg": [1e5, 4e4],
        "registros": [40, 12],
    }
)
FICHA_MENSUAL = pd.DataFrame(
    {
        "anio": [2024],
        "mes": [1],
        "hs6": ["392350"],
        "pais": ["ECU"],
        "valor_unitario": [10.0],
        "registros": [4],
    }
)


def _paquete(
    root: Path,
    *,
    version: int = 1,
    socios: pd.DataFrame = SOCIOS,
    hs4: pd.DataFrame = HS4,
    mensual: pd.DataFrame = FICHA_MENSUAL,
) -> Path:
    package = root / "radar"
    package.mkdir()
    INDICADORES.to_parquet(package / "subsector_indicadores.parquet", index=False)
    socios.to_parquet(package / "subsector_socios.parquet", index=False)
    hs4.to_parquet(package / "hs4_subsector.parquet", index=False)
    PARTIDAS.to_parquet(package / "subsector_partidas.parquet", index=False)
    FICHA_ANUAL.to_parquet(package / "ficha_anual.parquet", index=False)
    mensual.to_parquet(package / "ficha_mensual.parquet", index=False)
    (package / "meta.json").write_text('{"ultimo_mes_comparable": {"2024": 12}}', encoding="utf-8")
    write_manifest(
        package,
        source_inputs=[{"archivo": "Expo_2024.zip", "sha256": "0" * 64}],
        parameters={
            "contrato": "observatorio-radar",
            "contrato_version": version,
            "commit": "abc1234",
        },
    )
    return package


def test_importa_un_paquete_valido(tmp_path: Path) -> None:
    target = tmp_path / "observatorio"
    target.mkdir()
    (target / "tabla_vieja.parquet").write_bytes(b"x")

    import_package(_paquete(tmp_path), target)

    assert (target / "manifest.json").is_file()
    pd.testing.assert_frame_equal(pd.read_parquet(target / "subsector_socios.parquet"), SOCIOS)
    # Se publica el paquete entero: lo que ya no viene no sobrevive.
    assert not (target / "tabla_vieja.parquet").exists()
    verify_package(target)


def test_rechaza_un_archivo_alterado(tmp_path: Path) -> None:
    package = _paquete(tmp_path)
    SOCIOS.assign(X=[2e6]).to_parquet(package / "subsector_socios.parquet", index=False)
    target = tmp_path / "observatorio"

    with pytest.raises(RuntimeError, match="no coincide"):
        import_package(package, target)
    assert not target.exists()


def test_rechaza_un_paquete_sin_manifiesto(tmp_path: Path) -> None:
    package = _paquete(tmp_path)
    (package / "manifest.json").unlink()
    with pytest.raises(RuntimeError, match="Falta"):
        verify_package(package)


def test_rechaza_una_version_de_contrato_desconocida(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no soportada"):
        verify_package(_paquete(tmp_path, version=2))


def test_zonas_francas_no_pueden_ser_socios(tmp_path: Path) -> None:
    package = _paquete(tmp_path, socios=SOCIOS.assign(pais=["XCF"]))
    with pytest.raises(pandera.errors.SchemaErrors):
        verify_package(package)


def test_participacion_de_cada_hs4_suma_uno(tmp_path: Path) -> None:
    package = _paquete(tmp_path, hs4=HS4.assign(participacion=[1.0, 0.9, 0.3]))
    with pytest.raises(pandera.errors.SchemaErrors):
        verify_package(package)


def test_el_paquete_versionado_cumple_el_contrato() -> None:
    """Lo que está en data/processed/observatorio entró por el importador, no a mano."""
    verify_package(config.OBSERVATORIO_DIR)


def test_un_precio_mensual_con_pocos_registros_no_entra(tmp_path: Path) -> None:
    """El umbral de confidencialidad es parte del contrato, no una convención."""
    package = _paquete(tmp_path, mensual=FICHA_MENSUAL.assign(registros=[2]))
    with pytest.raises(pandera.errors.SchemaErrors):
        verify_package(package)
