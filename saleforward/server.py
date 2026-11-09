"""A stand-in for a payment API that takes an idempotency key.

Each request is a generator. A `yield` is a point where another request may run, so
a test or the simulator can interleave two requests at that point. The generator
returns (status, charge_id), where status is one of:
  charged      a new charge was made
  replayed     the key was seen before; the earlier charge is returned
  conflict     the key was seen before with a different amount
  in_progress  the key is claimed and its first request has not finished
"""
import sqlite3

MODES = ("lookup", "claim")


class PaymentServer:
    def __init__(self, mode):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        self.mode = mode
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        self.db.execute(
            "CREATE TABLE charges ("
            " charge_id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " amount_cents INTEGER NOT NULL,"
            " ref TEXT NOT NULL)"
        )
        # `lookup` keeps the key in a plain column: the code looks it up and then inserts,
        # and the database does not stop two inserts of the same key. `claim` makes the
        # key the primary key and takes it with one insert before any charge is made.
        key_column = "key TEXT PRIMARY KEY" if mode == "claim" else "key TEXT NOT NULL"
        self.db.execute(
            f"CREATE TABLE idem ({key_column}, amount_cents INTEGER NOT NULL, charge_id INTEGER)"
        )

    def charge(self, key, amount_cents, ref):
        if self.mode == "claim":
            return self._charge_claim(key, amount_cents, ref)
        return self._charge_lookup(key, amount_cents, ref)

    def _new_charge(self, amount_cents, ref):
        cur = self.db.execute(
            "INSERT INTO charges (amount_cents, ref) VALUES (?, ?)", (amount_cents, ref)
        )
        return cur.lastrowid

    def _charge_lookup(self, key, amount_cents, ref):
        seen = self.db.execute(
            "SELECT amount_cents, charge_id FROM idem WHERE key = ?", (key,)
        ).fetchone()
        yield
        if seen is not None:
            if seen[0] != amount_cents:
                return ("conflict", None)
            return ("replayed", seen[1])
        charge_id = self._new_charge(amount_cents, ref)
        self.db.execute(
            "INSERT INTO idem (key, amount_cents, charge_id) VALUES (?, ?, ?)",
            (key, amount_cents, charge_id),
        )
        return ("charged", charge_id)

    def _charge_claim(self, key, amount_cents, ref):
        claimed = self.db.execute(
            "INSERT INTO idem (key, amount_cents) VALUES (?, ?) ON CONFLICT (key) DO NOTHING",
            (key, amount_cents),
        ).rowcount == 1
        yield
        if claimed:
            charge_id = self._new_charge(amount_cents, ref)
            self.db.execute("UPDATE idem SET charge_id = ? WHERE key = ?", (charge_id, key))
            return ("charged", charge_id)
        stored_amount, charge_id = self.db.execute(
            "SELECT amount_cents, charge_id FROM idem WHERE key = ?", (key,)
        ).fetchone()
        if stored_amount != amount_cents:
            return ("conflict", None)
        if charge_id is None:
            return ("in_progress", None)
        return ("replayed", charge_id)

    def charges_by_ref(self):
        """{ref: (number of charges, total cents)} for the audit."""
        rows = self.db.execute(
            "SELECT ref, COUNT(*), SUM(amount_cents) FROM charges GROUP BY ref"
        ).fetchall()
        return {ref: (n, total) for ref, n, total in rows}


def drive(request):
    """Run one request to its end and return its result."""
    while True:
        try:
            next(request)
        except StopIteration as done:
            return done.value
