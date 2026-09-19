"""Tests must never create anything inside the protected result namespaces, even if a guard under test regresses."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROTECTED = tuple((ROOT / name).resolve() for name in ('results/b0-calibration', 'results/b0-suffix-calibration',
                                                            'results/crst-small-pilot'))


@pytest.fixture(autouse=True)
def b0_results_are_read_only(monkeypatch):
    original = Path.mkdir

    def guarded(self, *args, **kwargs):
        target = self.resolve()
        if any(target == root or root in target.parents for root in PROTECTED):
            pytest.fail(f'Tests must not create {target}')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'mkdir', guarded)


@pytest.fixture(autouse=True)
def pilot_results_are_never_touched():
    """The archived Small Pilot evidence must be identical after every test: nothing added, changed or removed."""
    base = ROOT / 'results/crst-small-pilot'

    def snapshot():
        return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in base.rglob('*') if p.is_file()}
    before = snapshot()
    yield
    assert snapshot() == before, 'A test changed the archived Small Pilot results'
