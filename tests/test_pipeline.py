"""Tests del pipeline: RCA tolerante y construcción on-demand. Sin red."""

import json
from pathlib import Path

import pandas as pd
import pytest

from tradefit import config
from tradefit.contracts import export_totals_schema
from tradefit.pipeline import build_snapshot as pipeline


def _totals(rows: list[tuple[str, str, int, float]]) -> pd.DataFrame:
    df = pd.DataFrame(
        rows, columns=[config.COL_SCOPE, config.COL_CMD, config.COL_YEAR, config.COL_VALUE]
    )
    validated: pd.DataFrame = export_totals_schema.validate(df)
    return validated


def test_rca_conocido_a_mano() -> None:
    # (900/1000) / (100/10000) = 0.9 / 0.01 = 90
    totals = _totals(
        [
            ("origin", "product", 2024, 900.0),
            ("origin", "total", 2024, 1000.0),
            ("world", "product", 2024, 100.0),
            ("world", "total", 2024, 10000.0),
        ]
    )
    assert pipeline._rca_from_totals(totals) == pytest.approx(90.0)


def test_rca_sin_exportaciones_del_origen_es_cero() -> None:
    totals = _totals(
        [
            ("origin", "total", 2024, 1000.0),
            ("world", "product", 2024, 100.0),
            ("world", "total", 2024, 10000.0),
        ]
    )
    assert pipeline._rca_from_totals(totals) == 0.0


def test_build_rechaza_partida_invalida() -> None:
    with pytest.raises(ValueError, match="Partida HS inválida"):
        pipeline.build_snapshot(source="stub", hs="09011")


def test_ensure_normaliza_y_no_reconstruye_si_existe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    snapshot_dir = tmp_path / "1701"
    snapshot_dir.mkdir()
    (snapshot_dir / "ranking.parquet").write_bytes(b"parquet-fake")
    (snapshot_dir / "meta.json").write_text(json.dumps({"hs_code": "1701"}), encoding="utf-8")

    def _explota(source: str = "comtrade", hs: str = config.HS_CODE) -> pd.DataFrame:
        raise AssertionError("No debe reconstruir un snapshot existente")

    monkeypatch.setattr(pipeline, "build_snapshot", _explota)
    assert pipeline.ensure_snapshot(" 17.01 ") == "1701"


def test_ensure_construye_si_falta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    built: list[str] = []
    monkeypatch.setattr(
        pipeline,
        "build_snapshot",
        lambda source, hs, on_stage=None: built.append(hs) or pd.DataFrame(),
    )
    pipeline.ensure_snapshot("1701")
    assert built == ["1701"]


def test_ensure_rechaza_partida_invalida() -> None:
    with pytest.raises(ValueError, match="Partida HS inválida"):
        pipeline.ensure_snapshot("no-es-hs")


def test_build_reporta_etapas_en_orden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    stages: list[str] = []
    pipeline.build_snapshot(source="stub", hs=config.HS_CODE, on_stage=stages.append)
    assert stages[0] == "Insumos locales de ejemplo (stub, sin red)"
    assert stages[-2] == "Calculando índices, estabilidad macro y ranking"
    assert stages[-1] == "Escribiendo el snapshot"


def test_build_sin_callback_no_falla(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    ranking = pipeline.build_snapshot(source="stub", hs=config.HS_CODE)
    assert not ranking.empty


def test_build_publica_manifiesto_y_stub_no_pisa_macro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El snapshot es verificable y el stub no contamina el macro compartido."""
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    macro_path = config.macro_context_parquet()
    macro_path.write_bytes(b"macro-real-previo")

    pipeline.build_snapshot(source="stub", hs=config.HS_CODE)

    assert config.snapshot_manifest_json(config.HS_CODE).exists()
    assert macro_path.read_bytes() == b"macro-real-previo"


def test_narrativa_del_snapshot_es_bilingue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    pipeline.build_snapshot(source="stub", hs=config.HS_CODE)
    narrative = json.loads(config.narrative_json(config.HS_CODE).read_text(encoding="utf-8"))
    assert set(narrative) == {"es", "en"}
    for lang in ("es", "en"):
        assert narrative[lang]["markets"], f"narrativa vacía en {lang!r}"
        assert narrative[lang]["recommendations"]
    # La etiqueta del producto curado va en el idioma de cada narrativa.
    es_text = " ".join(s for ss in narrative["es"]["markets"].values() for s in ss)
    en_text = " ".join(s for ss in narrative["en"]["markets"].values() for s in ss)
    assert "Café (HS 0901)" in es_text
    assert "Coffee (HS 0901)" in en_text
