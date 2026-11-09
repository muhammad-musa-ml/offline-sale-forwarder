import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from saleforward.journal import Journal

ROOT = Path(__file__).resolve().parent.parent


def test_oldest_sale_comes_first():
    j = Journal(":memory:")
    j.record("a", 500)
    j.record("b", 700)
    assert j.next_pending() == ("a", 500)


def test_sent_sale_is_no_longer_pending():
    j = Journal(":memory:")
    j.record("a", 500)
    j.record("b", 700)
    j.mark_sent("a")
    assert j.next_pending() == ("b", 700)
    assert j.pending_count() == 1


def test_recording_a_sale_twice_keeps_one_row():
    j = Journal(":memory:")
    j.record("a", 500)
    j.record("a", 500)
    assert j.pending_count() == 1


def test_recording_a_sale_again_with_another_amount_is_refused():
    j = Journal(":memory:")
    j.record("a", 500)
    with pytest.raises(ValueError):
        j.record("a", 600)


def test_a_zero_amount_is_refused():
    j = Journal(":memory:")
    with pytest.raises(sqlite3.IntegrityError):
        j.record("a", 0)


def test_pending_sale_survives_a_killed_process(tmp_path):
    path = tmp_path / "register.db"
    died = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "record_then_die.py"), str(ROOT), str(path)]
    )
    assert died.returncode == 1
    j = Journal(str(path))
    assert j.next_pending() == ("reg-0001", 1899)


def test_sent_state_survives_a_reopen(tmp_path):
    path = str(tmp_path / "register.db")
    j = Journal(path)
    j.record("a", 500)
    j.mark_sent("a")
    j.close()
    assert Journal(path).next_pending() is None
