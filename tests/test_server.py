import itertools

import pytest

from saleforward.server import MODES, PaymentServer, drive


@pytest.mark.parametrize("mode", MODES)
def test_a_repeated_key_returns_the_first_charge(mode):
    s = PaymentServer(mode)
    first = drive(s.charge("k1", 1899, "sale-1"))
    again = drive(s.charge("k1", 1899, "sale-1"))
    assert first[0] == "charged"
    assert again == ("replayed", first[1])
    assert s.charges_by_ref() == {"sale-1": (1, 1899)}


@pytest.mark.parametrize("mode", MODES)
def test_a_new_key_for_the_same_sale_charges_again(mode):
    s = PaymentServer(mode)
    drive(s.charge("k1", 1899, "sale-1"))
    drive(s.charge("k2", 1899, "sale-1"))
    assert s.charges_by_ref() == {"sale-1": (2, 3798)}


@pytest.mark.parametrize("mode", MODES)
def test_a_key_reused_with_another_amount_is_a_conflict(mode):
    s = PaymentServer(mode)
    drive(s.charge("k1", 1899, "sale-1"))
    assert drive(s.charge("k1", 2500, "sale-1")) == ("conflict", None)
    assert s.charges_by_ref() == {"sale-1": (1, 1899)}


def _interleavings(a_steps, b_steps):
    """Every order in which two requests with these step counts can run."""
    total = a_steps + b_steps
    for a_slots in itertools.combinations(range(total), a_steps):
        yield ["a" if i in a_slots else "b" for i in range(total)]


def _run(mode, order):
    s = PaymentServer(mode)
    requests = {"a": s.charge("k1", 1899, "sale-1"), "b": s.charge("k1", 1899, "sale-1")}
    results = {}
    for who in order:
        try:
            next(requests[who])
        except StopIteration as done:
            results[who] = done.value
    return s.charges_by_ref().get("sale-1", (0, 0))[0], results


def test_lookup_then_insert_charges_twice_in_four_of_six_orders():
    # Each request takes two steps. In the orders where both look the key up first,
    # neither sees the other, and both insert.
    counts = [_run("lookup", order)[0] for order in _interleavings(2, 2)]
    assert len(counts) == 6
    assert sorted(counts) == [1, 1, 2, 2, 2, 2]


def test_claiming_the_key_first_never_charges_twice_in_any_order():
    for order in _interleavings(2, 2):
        count, results = _run("claim", order)
        assert count == 1
        assert sorted(r[0] for r in results.values()) in (
            ["charged", "in_progress"],
            ["charged", "replayed"],
        )
