"""Tests must never create anything inside the B0 result namespaces, even if a guard under test regresses."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROTECTED = tuple((ROOT / name).resolve() for name in ('results/b0-calibration', 'results/b0-suffix-calibration'))


@pytest.fixture(autouse=True)
def b0_results_are_read_only(monkeypatch):
    original = Path.mkdir

    def guarded(self, *args, **kwargs):
        target = self.resolve()
        if any(target == root or root in target.parents for root in PROTECTED):
            pytest.fail(f'Tests must not create {target}')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'mkdir', guarded)
