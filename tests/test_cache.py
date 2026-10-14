"""Tests for JSON stage cache persistence."""

from pathlib import Path

from pipeline.run import _read_cache, _write_cache


def test_cache_round_trip_and_signature_invalidation(tmp_path: Path) -> None:
    """Cached values reload for the same signature and miss on changed input."""
    cache = tmp_path / "stage.json"
    _write_cache(cache, "signature-a", {"text": "saved"}, enabled=True)
    assert _read_cache(cache, "signature-a", enabled=True) == {"text": "saved"}
    assert _read_cache(cache, "signature-b", enabled=True) is None
