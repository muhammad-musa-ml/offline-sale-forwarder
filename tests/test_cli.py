import json
from pathlib import Path

from saleforward.__main__ import main, run_one_fault, run_table

ROOT = Path(__file__).resolve().parent.parent


def test_the_first_block_of_the_committed_table_matches_a_fresh_run():
    committed = json.loads((ROOT / "results" / "table.json").read_text(encoding="utf-8"))
    fresh = run_table(200, 1)
    for new, old in zip(fresh["setups"], committed["setups"]):
        assert (new["key"], new["server"]) == (old["key"], old["server"])
        assert new["blocks"][0] == old["blocks"][0]


def test_stored_key_with_a_claiming_server_has_no_duplicate_in_the_committed_table():
    committed = json.loads((ROOT / "results" / "table.json").read_text(encoding="utf-8"))
    row = next(r for r in committed["setups"] if (r["key"], r["server"]) == ("stored", "claim"))
    assert all(b["runs_with_a_duplicate"] == 0 for b in row["blocks"])
    assert all(b["uncharged_sales"] == 0 and b["runs_not_drained"] == 0 for b in row["blocks"])


def test_explain_shows_two_charges_for_one_sale(capsys):
    assert main(["explain", "--key", "fresh", "--server", "claim", "--seed", "0"]) == 0
    out = capsys.readouterr().out
    assert "charged twice" in out
    assert out.count(": charged") == 2
    assert "lost" in out


def test_explain_finds_nothing_for_a_stored_key_and_a_claiming_server(capsys):
    assert main(["explain", "--key", "stored", "--server", "claim", "--limit", "40"]) == 0
    assert "no sale charged twice" in capsys.readouterr().out


def test_one_fault_at_a_time_points_at_the_lost_reply_for_a_new_key_per_try():
    rows = run_one_fault(20)
    by = {(r["key"], r["server"], r["fault"]): r["runs_with_a_duplicate"] for r in rows}
    lost_reply = by[("fresh", "claim", "reply lost, 30%")]
    quiet = by[("fresh", "claim", "none (slow replies only)")]
    assert lost_reply > quiet
    assert all(n == 0 for (key, server, _), n in by.items() if (key, server) == ("stored", "claim"))
