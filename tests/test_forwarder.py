from types import SimpleNamespace

import pytest

from saleforward.forwarder import forward
from saleforward.journal import Journal


class StubWorld:
    """Answers each send with the next scripted reply."""

    timeout = 3

    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []

    def fresh_key(self, sale_id):
        return f"{sale_id}/new{len(self.sent) + 1}"

    def send(self, tag, key, amount, ref):
        self.sent.append(key)
        return SimpleNamespace(reply=self.replies.pop(0))

    def crash_after_reply(self):
        return False

    def log(self, who, ref, text):
        pass


def _drain(replies, policy="stored"):
    journal = Journal(":memory:")
    journal.record("a", 500)
    world = StubWorld(replies)
    for _ in forward(journal, world, policy, "register-1"):
        pass
    return journal, world


def test_a_charged_reply_marks_the_sale_sent():
    journal, world = _drain([("charged", 1)])
    assert world.sent == ["a"]
    assert journal.pending_count() == 0


def test_a_replayed_reply_marks_the_sale_sent():
    journal, world = _drain([("replayed", 1)])
    assert world.sent == ["a"]
    assert journal.pending_count() == 0


def test_an_in_progress_reply_leaves_the_sale_pending_and_sends_it_again():
    journal, world = _drain([("in_progress", None), ("charged", 1)])
    assert world.sent == ["a", "a"]
    assert journal.pending_count() == 0


def test_a_conflict_reply_stops_the_loop():
    with pytest.raises(RuntimeError):
        _drain([("conflict", None)])


def test_the_fresh_policy_sends_a_new_key_and_the_stored_policy_the_sale_id():
    _, fresh = _drain([("in_progress", None), ("charged", 1)], policy="fresh")
    _, stored = _drain([("in_progress", None), ("charged", 1)], policy="stored")
    assert fresh.sent == ["a/new1", "a/new2"]
    assert stored.sent == ["a", "a"]
