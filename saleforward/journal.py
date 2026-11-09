"""The register's own record of sales taken while it may be offline."""
import sqlite3


class Journal:
    def __init__(self, path):
        self.db = sqlite3.connect(path, isolation_level=None)
        if path != ":memory:":
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS sales ("
            " seq INTEGER PRIMARY KEY AUTOINCREMENT,"
            " sale_id TEXT NOT NULL UNIQUE,"
            " amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),"
            " state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'sent')))"
        )

    def record(self, sale_id, amount_cents):
        """Store a sale. Recording the same sale again keeps one row."""
        self.db.execute(
            "INSERT INTO sales (sale_id, amount_cents) VALUES (?, ?)"
            " ON CONFLICT (sale_id) DO NOTHING",
            (sale_id, amount_cents),
        )
        stored = self.db.execute(
            "SELECT amount_cents FROM sales WHERE sale_id = ?", (sale_id,)
        ).fetchone()[0]
        if stored != amount_cents:
            raise ValueError(f"sale {sale_id} is already recorded for {stored} cents")

    def next_pending(self):
        """The oldest sale not yet confirmed by the server, as (sale_id, amount_cents)."""
        return self.db.execute(
            "SELECT sale_id, amount_cents FROM sales WHERE state = 'pending' ORDER BY seq LIMIT 1"
        ).fetchone()

    def mark_sent(self, sale_id):
        self.db.execute("UPDATE sales SET state = 'sent' WHERE sale_id = ?", (sale_id,))

    def pending_count(self):
        return self.db.execute("SELECT COUNT(*) FROM sales WHERE state = 'pending'").fetchone()[0]

    def close(self):
        self.db.close()
