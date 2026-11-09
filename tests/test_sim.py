import pytest

from saleforward.sim import World


class Scripted(World):
    """A run where the network fault happens at a chosen send or reply and nowhere else."""

    def __init__(self, policy, mode, seed=1, lose_request_at=(), lose_reply_at=(), crash_at=()):
        super().__init__(seed, policy, mode, sales=3, lose_request=0, lose_reply=0, crash=0, second=0)
        self.lose_request_at = lose_request_at
        self.lose_reply_at = lose_reply_at
        self.crash_at = crash_at
        self.sends = 0
        self.replies = 0

    def send(self, tag, key, amount, ref):
        self.sends += 1
        self.p_lose_request = 1.0 if self.sends in self.lose_request_at else 0.0
        request = super().send(tag, key, amount, ref)
        request.lose_reply = self.sends in self.lose_reply_at
        return request

    def crash_after_reply(self):
        self.replies += 1
        return self.replies in self.crash_at


MODES = ("lookup", "claim")


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("seed", range(5))
def test_a_lost_reply_does_not_duplicate_a_charge_when_the_key_is_stored(mode, seed):
    result = Scripted("stored", mode, seed, lose_reply_at=(1,)).run()
    assert result["drained"] and result["duplicated"] == 0 and result["lost"] == 0


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("seed", range(5))
def test_a_lost_reply_duplicates_a_charge_when_each_try_makes_a_new_key(mode, seed):
    result = Scripted("fresh", mode, seed, lose_reply_at=(1,)).run()
    assert result["drained"] and result["duplicated"] == 1 and result["lost"] == 0
    assert result["extra_cents"] > 0


@pytest.mark.parametrize("policy", ("fresh", "stored"))
@pytest.mark.parametrize("mode", MODES)
def test_a_lost_request_is_sent_again_and_charged_once(policy, mode):
    result = Scripted(policy, mode, lose_request_at=(1,)).run()
    assert result["drained"] and result["lost"] == 0 and result["duplicated"] == 0


@pytest.mark.parametrize("mode", MODES)
def test_a_crash_after_the_reply_does_not_duplicate_a_charge_when_the_key_is_stored(mode):
    result = Scripted("stored", mode, crash_at=(1,)).run()
    assert result["drained"] and result["duplicated"] == 0 and result["lost"] == 0


@pytest.mark.parametrize("mode", MODES)
def test_a_crash_after_the_reply_duplicates_a_charge_when_each_try_makes_a_new_key(mode):
    result = Scripted("fresh", mode, crash_at=(1,)).run()
    assert result["drained"] and result["duplicated"] == 1 and result["lost"] == 0


def test_the_same_seed_gives_the_same_run():
    a = World(7, "fresh", "lookup")
    b = World(7, "fresh", "lookup")
    assert a.run() == b.run()
    assert a.events == b.events


def _many(policy, mode, seeds=100):
    return [World(seed, policy, mode).run() for seed in range(seeds)]


@pytest.mark.parametrize("policy", ("fresh", "stored"))
@pytest.mark.parametrize("mode", MODES)
def test_every_run_drains_and_no_sale_goes_uncharged(policy, mode):
    for result in _many(policy, mode, 100):
        assert result["drained"]
        assert result["lost"] == 0


def test_stored_key_with_a_claiming_server_never_charges_a_sale_twice():
    assert all(r["duplicated"] == 0 for r in _many("stored", "claim"))


def test_a_new_key_per_try_duplicates_charges_against_either_server():
    assert any(r["duplicated"] > 0 for r in _many("fresh", "claim"))
    assert any(r["duplicated"] > 0 for r in _many("fresh", "lookup"))


def test_a_stored_key_still_duplicates_against_a_server_that_looks_up_then_inserts():
    assert any(r["duplicated"] > 0 for r in _many("stored", "lookup"))
