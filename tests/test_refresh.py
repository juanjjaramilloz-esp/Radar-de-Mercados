"""Política y orquestación del refresh automático."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tradefit.ingest.cache import write_json_cache
from tradefit.pipeline import refresh


def _cache(path: Path, retrieved_at: str) -> None:
    write_json_cache(
        path,
        {"data": []},
        source="fixture",
        parameters={},
        retrieved_at=retrieved_at,
    )


def test_cache_group_due_respeta_edad(tmp_path: Path) -> None:
    """Un caché dentro del TTL no vence; en el límite sí."""
    cache = tmp_path / "source.json"
    _cache(cache, "2026-07-01T00:00:00+00:00")
    now = datetime(2026, 7, 31, tzinfo=UTC)

    assert refresh.cache_group_due([cache], 31, now) is False
    assert refresh.cache_group_due([cache], 30, now) is True


def test_cache_group_due_si_falta_sidecar(tmp_path: Path) -> None:
    """Los cachés legacy entran al primer refresh programado."""
    cache = tmp_path / "legacy.json"
    cache.write_text("{}", encoding="utf-8")

    assert refresh.cache_group_due([cache], 60, datetime.now(UTC)) is True


def test_dry_run_no_construye(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """El plan puede inspeccionarse sin red ni escrituras."""
    cache = tmp_path / "missing.json"
    monkeypatch.setattr(
        refresh, "_cache_groups", lambda products: {s: [cache] for s in refresh.SOURCES}
    )
    monkeypatch.setattr(
        refresh,
        "build_snapshot",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("no debe construir")),
    )

    report = refresh.refresh_catalog(products=["0901"], dry_run=True)

    assert report["sources"] == ["comtrade", "wdi", "wits"]


def test_refresh_wdi_reconstruye_catalogo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Una fuente compartida se descarga una vez y reconstruye cada producto."""
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        refresh.worldbank,
        "load_wdi_macro",
        lambda force=False: calls.append(("wdi", force)),
    )
    monkeypatch.setattr(
        refresh,
        "build_snapshot",
        lambda **kwargs: calls.append(("build", kwargs["hs"])),
    )
    monkeypatch.setattr(refresh, "run_backtest", lambda: calls.append(("backtest", True)))

    report = refresh.refresh_catalog(
        products=["0901", "0603"], requested_sources=frozenset({"wdi"})
    )

    assert report["sources"] == ["wdi"]
    assert calls == [("wdi", True), ("build", "0901"), ("build", "0603"), ("backtest", True)]


def test_refresh_comtrade_exige_secreto(monkeypatch: pytest.MonkeyPatch) -> None:
    """La automatización falla claro antes de intentar el preview truncado."""
    monkeypatch.setattr(refresh, "load_dotenv", lambda: False)
    monkeypatch.delenv("COMTRADE_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="COMTRADE_API_KEY"):
        refresh.refresh_catalog(products=["0901"], requested_sources=frozenset({"comtrade"}))
