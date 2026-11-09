"""The loop that sends journaled sales to the payment API once the register is online."""

POLICIES = ("fresh", "stored")


class Crash(Exception):
    """The register process died."""


def forward(journal, world, policy, tag, delay=0):
    """A generator: each `yield` is a point where another task may run.

    policy "stored" sends the sale id as the idempotency key on every try.
    policy "fresh" makes a new key for every try.
    """
    for _ in range(delay):
        yield
    while True:
        yield
        row = journal.next_pending()
        if row is None:
            return
        sale_id, amount = row
        key = sale_id if policy == "stored" else world.fresh_key(sale_id)
        yield
        request = world.send(tag, key, amount, sale_id)
        for _ in range(world.timeout):
            yield
            if request.reply is not None:
                break
        else:
            world.log(tag, sale_id, f"no reply for {key}, trying again")
            continue
        if world.crash_after_reply():
            world.log(tag, sale_id, f"register process died holding the reply for {key}")
            raise Crash(tag)
        status = request.reply[0]
        if status in ("charged", "replayed"):
            yield
            journal.mark_sent(sale_id)
            world.log(tag, sale_id, f"marked sent after {status}")
        elif status != "in_progress":
            raise RuntimeError(f"unexpected status {status} for key {key}")
