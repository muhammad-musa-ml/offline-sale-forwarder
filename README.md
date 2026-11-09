# offline-sale-forwarder

I wrote a small model of a register that keeps taking sales while the network is down and sends them to a payment API when it comes back. It checks one thing: after a lost reply, a dead process or a second sender, is each sale charged once?

I ran it on Python 3.13 only. It uses the standard library; pytest is needed for the tests.

## Why

Margin's site lists an offline mode for its liquor-store registers and says it has no duplicate charges. A developer on the Stripe Terminal Android tracker reports that one stored offline payment was forwarded twice and produced two succeeded charges ([issue 747](https://github.com/stripe/stripe-terminal-android/issues/747), open when I read it on 2026-11-09). I have not reproduced that report, and this repository does not use Stripe's SDK. It is my own model of the same kind of failure, and of the two choices that decide whether it happens: which key the register sends, and what the server does with a key it has seen.

## What is in it

- `saleforward/journal.py`: the register's journal, a SQLite file. A sale is written before any network call and marked sent only after the server answers.
- `saleforward/server.py`: a stand-in payment API that takes an idempotency key. In `lookup` mode it looks the key up and then inserts. In `claim` mode it takes the key with one insert first. Each request is a generator, so a test can run two of them in every possible order.
- `saleforward/forwarder.py`: the send loop. Key `stored` sends the sale id on every try. Key `fresh` makes a new key on every try.
- `saleforward/sim.py`: one seeded run. Twelve queued sales of 5.00 to 99.99 dollars drain through these faults: a request is lost with probability 0.1, a reply with 0.3, the register process dies after a reply with 0.1 (a new one starts after 0 to 5 turns of its own), and in half the runs a second forwarder starts after waiting 1 to 29 turns of its own. A forwarder waits 8 of its own turns for a reply and then sends again, so a slow server also causes a retry. A seeded scheduler picks which task runs next, so a run repeats exactly.

## Run

```sh
python -m saleforward table --out results/table.json
python -m saleforward faults
python -m saleforward explain --key fresh --server claim
python -m pytest
```

`table` runs the four setups over three blocks of 200 seeds. `faults` turns the faults on one at a time. `explain` prints the history of one sale that was charged twice.

## Results

From `python -m saleforward table`:

```
200 runs per block, 12 sales per run
key    server  runs with a duplicate, per block    sales charged twice per run (min/median/max)    extra dollars, per block
fresh  lookup  200/200, 200/200, 200/200           1/7.0/12                                        106820, 116115, 112643
fresh  claim   200/200, 200/200, 200/200           1/7.0/12                                        106820, 116115, 112643
stored lookup  88/200, 96/200, 93/200              0/0.0/5                                         7799, 8611, 8898
stored claim   0/200, 0/200, 0/200                 0/0.0/0                                         0, 0, 0
```

- A new key on every try charged some sale twice in all 600 runs, with a median of 7 of 12 sales. The two servers give identical rows because the same seeds give the same faults and a new key never matches an old one.
- The sale id as the key, against a server that looks up and then inserts, still charged some sale twice in 88, 96 and 93 of 200 runs, and at most 5 sales in one run.
- The sale id as the key, against a server that claims the key first, charged no sale twice in any of the 600 runs.
- In every run of every setup, each sale was charged at least once and the journal drained. The committed table is `results/table.json`, and a test reruns its first block and compares.

From `python -m saleforward faults`, runs with a duplicate out of 200 when only one fault is on:

```
key    server  only this fault is on               runs with a duplicate
fresh  claim   none (slow replies only)            48/200
fresh  claim   request lost, 10%                   43/200
fresh  claim   reply lost, 30%                     199/200
fresh  claim   process dies after a reply, 10%     173/200
fresh  claim   second forwarder, 50% of runs       122/200
stored lookup  none (slow replies only)            13/200
stored lookup  request lost, 10%                   10/200
stored lookup  reply lost, 30%                     13/200
stored lookup  process dies after a reply, 10%     14/200
stored lookup  second forwarder, 50% of runs       92/200
stored claim   none (slow replies only)            0/200
stored claim   request lost, 10%                   0/200
stored claim   reply lost, 30%                     0/200
stored claim   process dies after a reply, 10%     0/200
stored claim   second forwarder, 50% of runs       0/200
```

A lost reply or a dead process alone breaks the new-key-per-try design, because the sale is still pending when the register tries again. Against the looking-up server, the stored key fails mostly when a second forwarder runs (92 of 200 runs) and rarely otherwise (10 to 14 of 200), including when the only fault is a slow reply (13 of 200).

`explain --key fresh --server claim` prints one case:

```
key=fresh server=claim seed=0: 3 of 12 sales charged twice, 22924 cents extra
first one: sale-004, 6211 cents
  tick   32  register-1  sent key sale-004/try-5
  tick   35  server      key sale-004/try-5: charged
  tick   35  server      reply to key sale-004/try-5 lost
  tick   42  register-1  no reply for sale-004/try-5, trying again
  tick   44  register-1  sent key sale-004/try-6
  tick   48  server      key sale-004/try-6: charged
  tick   50  register-1  marked sent after charged
```

The tests also run two requests with the same key in all 6 possible orders: the looking-up server charges twice in 4 of them, the claiming server in none.

## What this does not show

- It is a model. There is no card, reader, real network or real payment service. The server is SQLite in memory, and the error cases (`conflict`, `in_progress`) are my design, not a copy of any provider's behavior.
- The fault rates are my choices. The counts show which designs fail and which fault causes each failure. They say nothing about how often a real register would hit one.
- A process death is an exception in the simulation. The only real process death is in the journal test, which ends a process without closing the journal right after it records a sale.
- The simulation does not crash the server. If the claiming server died after taking a key and before charging, that key would stay claimed.
- Interleavings are chosen by a seeded scheduler at `yield` points, not by threads or the operating system.
- It does not cover refunds, partial captures, taxes or inventory.
