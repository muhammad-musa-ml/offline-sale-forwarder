import argparse
import json
import statistics
import sys

from .forwarder import POLICIES
from .server import MODES
from .sim import World

CONFIGS = [(policy, mode) for policy in POLICIES for mode in MODES]


def run_table(seeds, blocks):
    table = []
    for policy, mode in CONFIGS:
        per_block = []
        per_run = []
        for block in range(blocks):
            results = [World(seed, policy, mode).run() for seed in range(block * seeds, (block + 1) * seeds)]
            per_run += [r["duplicated"] for r in results]
            per_block.append({
                "seeds": f"{block * seeds}-{(block + 1) * seeds - 1}",
                "runs_with_a_duplicate": sum(1 for r in results if r["duplicated"] > 0),
                "sales_charged_twice": sum(r["duplicated"] for r in results),
                "extra_dollars": round(sum(r["extra_cents"] for r in results) / 100, 2),
                "uncharged_sales": sum(r["lost"] for r in results),
                "runs_not_drained": sum(1 for r in results if not r["drained"]),
            })
        table.append({
            "key": policy,
            "server": mode,
            "blocks": per_block,
            "per_run_sales_charged_twice": {
                "min": min(per_run),
                "median": statistics.median(per_run),
                "max": max(per_run),
            },
        })
    return {"runs_per_block": seeds, "sales_per_run": 12, "setups": table}


def format_table(result):
    n = result["runs_per_block"]
    lines = [f"{n} runs per block, {result['sales_per_run']} sales per run"]
    lines.append(f"{'key':<7}{'server':<8}{'runs with a duplicate, per block':<36}{'sales charged twice per run (min/median/max)':<48}{'extra dollars, per block'}")
    for row in result["setups"]:
        per_block = ", ".join(f"{b['runs_with_a_duplicate']}/{n}" for b in row["blocks"])
        spread = row["per_run_sales_charged_twice"]
        dollars = ", ".join(f"{b['extra_dollars']:.0f}" for b in row["blocks"])
        lines.append(
            f"{row['key']:<7}{row['server']:<8}{per_block:<36}"
            f"{str(spread['min']) + '/' + str(spread['median']) + '/' + str(spread['max']):<48}{dollars}"
        )
    return "\n".join(lines)


QUIET = dict(lose_request=0, lose_reply=0, crash=0, second=0)
ONE_FAULT = [
    ("none (slow replies only)", {}),
    ("request lost, 10%", {"lose_request": 0.1}),
    ("reply lost, 30%", {"lose_reply": 0.3}),
    ("process dies after a reply, 10%", {"crash": 0.1}),
    ("second forwarder, 50% of runs", {"second": 0.5}),
]


def run_one_fault(seeds):
    rows = []
    for policy, mode in (("fresh", "claim"), ("stored", "lookup"), ("stored", "claim")):
        for label, extra in ONE_FAULT:
            knobs = {**QUIET, **extra}
            results = [World(s, policy, mode, **knobs).run() for s in range(seeds)]
            rows.append({
                "key": policy,
                "server": mode,
                "fault": label,
                "runs_with_a_duplicate": sum(1 for r in results if r["duplicated"] > 0),
                "runs": seeds,
            })
    return rows


def format_one_fault(rows):
    lines = [f"{'key':<7}{'server':<8}{'only this fault is on':<36}runs with a duplicate"]
    for row in rows:
        lines.append(f"{row['key']:<7}{row['server']:<8}{row['fault']:<36}{row['runs_with_a_duplicate']}/{row['runs']}")
    return "\n".join(lines)


def explain(policy, mode, seed, limit):
    seeds = [seed] if seed is not None else range(limit)
    for s in seeds:
        world = World(s, policy, mode)
        result = world.run()
        if result["duplicated"] == 0:
            continue
        ref = result["duplicated_refs"][0]
        print(f"key={policy} server={mode} seed={s}: {result['duplicated']} of {result['sales']} sales "
              f"charged twice, {result['extra_cents']} cents extra")
        print(f"first one: {ref}, {world.amounts[ref]} cents")
        for tick, who, event_ref, text in world.events:
            if event_ref == ref:
                print(f"  tick {tick:>4}  {who:<11} {text}")
        return 0
    print(f"key={policy} server={mode}: no sale charged twice in "
          f"{'seed ' + str(seed) if seed is not None else 'seeds 0-' + str(limit - 1)}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="saleforward")
    sub = parser.add_subparsers(dest="command", required=True)
    t = sub.add_parser("table", help="run every setup over blocks of seeds")
    t.add_argument("--seeds", type=int, default=200, help="runs per block")
    t.add_argument("--blocks", type=int, default=3)
    t.add_argument("--out", help="also write the result as JSON to this path")
    f = sub.add_parser("faults", help="turn the faults on one at a time")
    f.add_argument("--seeds", type=int, default=200)
    e = sub.add_parser("explain", help="print the history of one sale that was charged twice")
    e.add_argument("--key", choices=POLICIES, default="fresh")
    e.add_argument("--server", choices=MODES, default="claim")
    e.add_argument("--seed", type=int, help="default: the first seed that charges a sale twice")
    e.add_argument("--limit", type=int, default=1000, help="how many seeds to try when no seed is given")
    args = parser.parse_args(argv)
    if args.command == "table":
        result = run_table(args.seeds, args.blocks)
        print(format_table(result))
        if args.out:
            with open(args.out, "w", encoding="utf-8", newline="\n") as f:
                json.dump(result, f, indent=2)
                f.write("\n")
        return 0
    if args.command == "faults":
        print(format_one_fault(run_one_fault(args.seeds)))
        return 0
    return explain(args.key, args.server, args.seed, args.limit)


if __name__ == "__main__":
    sys.exit(main())
