"""One seeded run: a register with queued sales drains into a payment API through a bad network."""
import random

from .forwarder import POLICIES, Crash, forward
from .journal import Journal
from .server import MODES, PaymentServer

MAX_TICKS = 200_000


class Request:
    def __init__(self, key, amount, ref, lose_reply):
        self.key = key
        self.amount = amount
        self.ref = ref
        self.lose_reply = lose_reply
        self.reply = None


class World:
    def __init__(self, seed, policy, mode, sales=12, lose_request=0.1, lose_reply=0.3,
                 crash=0.1, second=0.5, timeout=8):
        if policy not in POLICIES or mode not in MODES:
            raise ValueError("unknown policy or mode")
        self.policy = policy
        self.timeout = timeout
        self.p_lose_request = lose_request
        self.p_lose_reply = lose_reply
        self.p_crash = crash
        self.p_second = second
        self.sched = random.Random(seed)
        self.faults = random.Random(seed + 1_000_000)
        self.server = PaymentServer(mode)
        self.journal = Journal(":memory:")
        self.amounts = {}
        for n in range(sales):
            sale_id = f"sale-{n:03d}"
            self.amounts[sale_id] = self.faults.randrange(500, 10_000)
            self.journal.record(sale_id, self.amounts[sale_id])
        self.tasks = []
        self.events = []
        self.tick = 0
        self._tries = {}
        self._forwarders = 0

    def log(self, who, ref, text):
        self.events.append((self.tick, who, ref, text))

    def fresh_key(self, sale_id):
        self._tries[sale_id] = self._tries.get(sale_id, 0) + 1
        return f"{sale_id}/try-{self._tries[sale_id]}"

    def crash_after_reply(self):
        return self.faults.random() < self.p_crash

    def send(self, tag, key, amount, ref):
        request = Request(key, amount, ref, self.faults.random() < self.p_lose_reply)
        if self.faults.random() < self.p_lose_request:
            self.log(tag, ref, f"request with key {key} lost before the server")
            return request
        self.log(tag, ref, f"sent key {key}")
        self.tasks.append(("server", self._serve(request)))
        return request

    def _serve(self, request):
        result = yield from self.server.charge(request.key, request.amount, request.ref)
        self.log("server", request.ref, f"key {request.key}: {result[0]}")
        if request.lose_reply:
            self.log("server", request.ref, f"reply to key {request.key} lost")
        else:
            request.reply = result

    def _spawn_forwarder(self, delay):
        self._forwarders += 1
        tag = f"register-{self._forwarders}"
        self.tasks.append((tag, forward(self.journal, self, self.policy, tag, delay)))

    def run(self):
        self._spawn_forwarder(0)
        if self.faults.random() < self.p_second:
            self._spawn_forwarder(self.faults.randrange(1, 30))
        while self.tasks and self.tick < MAX_TICKS:
            self.tick += 1
            task = self.sched.choice(self.tasks)
            try:
                next(task[1])
            except StopIteration:
                self.tasks.remove(task)
            except Crash:
                self.tasks.remove(task)
                self._spawn_forwarder(self.faults.randrange(0, 6))
        return self.audit()

    def audit(self):
        by_ref = self.server.charges_by_ref()
        duplicated = [ref for ref, (n, _) in by_ref.items() if n > 1]
        extra = sum(by_ref[ref][1] - self.amounts[ref] for ref in duplicated)
        lost = [ref for ref in self.amounts if ref not in by_ref]
        return {
            "sales": len(self.amounts),
            "duplicated": len(duplicated),
            "duplicated_refs": duplicated,
            "extra_cents": extra,
            "lost": len(lost),
            "drained": self.journal.pending_count() == 0 and not self.tasks,
            "ticks": self.tick,
        }
