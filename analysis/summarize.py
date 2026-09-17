#!/usr/bin/env python3
import argparse
import csv
import random
from collections import defaultdict


def pct(xs, q):
    # linear interpolation between closest ranks
    s = sorted(xs)
    if not s:
        return float("nan")
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def boot_ci(xs, q, reps=2000, seed=0):
    rng = random.Random(seed)
    est = sorted(pct([rng.choice(xs) for _ in xs], q) for _ in range(reps))
    return est[int(0.025 * reps)], est[int(0.975 * reps) - 1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="+")
    ap.add_argument("--by", default="path,model,prompt_id,loss_pct,delay_ms")
    args = ap.parse_args()
    keys = args.by.split(",")

    groups = defaultdict(list)
    for path in args.csv:
        with open(path) as f:
            for r in csv.DictReader(f):
                if r["warmup"] == "1":
                    continue
                groups[tuple(r[k] for k in keys)].append(r)

    print("\t".join(keys + ["n", "fail_pct", "p50_ms", "p95_ms", "p95_ci", "p99_ms", "p99_ci", "total_p50_ms"]))
    for g, rows in sorted(groups.items()):
        ok = [r for r in rows if r["ok"] == "1"]
        ttft = [float(r["ttft_ms"]) for r in ok if r["ttft_ms"]]
        total = [float(r["total_ms"]) for r in ok if r["total_ms"]]
        fail = 100 * (len(rows) - len(ok)) / len(rows)
        c95, c99 = boot_ci(ttft, 0.95), boot_ci(ttft, 0.99)
        print("\t".join(list(g) + [
            str(len(rows)), f"{fail:.1f}",
            f"{pct(ttft, .5):.1f}", f"{pct(ttft, .95):.1f}", f"[{c95[0]:.1f}, {c95[1]:.1f}]",
            f"{pct(ttft, .99):.1f}", f"[{c99[0]:.1f}, {c99[1]:.1f}]", f"{pct(total, .5):.1f}",
        ]))


if __name__ == "__main__":
    main()
