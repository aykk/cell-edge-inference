#!/usr/bin/env python3
import argparse
import csv
import getpass
import json
import os
import random
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "harness"))
import impair  # noqa: E402

MODELS = ["qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:3b"]
PROMPTS = ["short", "long"]
LOSS_AXIS = [0, 0.5, 1, 2, 5, 10, 20]
DELAY_AXIS = [20, 50, 100, 200]
CROSS = [(1, 50), (1, 100), (5, 50), (5, 100)]


def network_conditions():
    conds = [(loss, 0) for loss in LOSS_AXIS]
    conds += [(0, d) for d in DELAY_AXIS]
    conds += CROSS
    return conds


def build_plan(seed, sentinel_every):
    cells = []
    for loss, delay in network_conditions():
        for m in MODELS:
            for p in PROMPTS:
                cells.append({"path": "ran", "model": m, "prompt": p, "loss": loss, "delay": delay})
    for m in MODELS:
        for p in PROMPTS:
            cells.append({"path": "loopback", "model": m, "prompt": p, "loss": 0, "delay": 0})
    # shuffled so slow drift in the machine does not line up with any one condition
    random.Random(seed).shuffle(cells)
    plan = []
    for i, c in enumerate(cells):
        if i % sentinel_every == 0:
            plan.append({"path": "ran", "model": MODELS[0], "prompt": "short", "loss": 0, "delay": 0, "sentinel": True})
        plan.append(dict(c, sentinel=False))
    plan.append({"path": "ran", "model": MODELS[0], "prompt": "short", "loss": 0, "delay": 0, "sentinel": True})
    for i, c in enumerate(plan):
        c["cell"] = f"c{i:03d}"
    return plan


def ran_healthy():
    r = subprocess.run(["sudo", "ip", "netns", "exec", "ue1", "ping", "-q", "-c", "5", "-W", "2", "-i", "0.2", "10.45.0.1"],
                       capture_output=True, text=True)
    return r.returncode == 0


def oom_kills():
    r = subprocess.run(["sudo", "dmesg"], capture_output=True, text=True)
    return r.stdout.count("Out of memory: Killed process")


def restart_ran():
    subprocess.run([os.path.join(ROOT, "infra", "ran.sh"), "start"], check=False)


def log_event(path, cell, event, detail=""):
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["wall", "cell", "event", "detail"])
        w.writerow([round(time.time(), 3), cell, event, detail])


def read_events(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def run_cell(c, attempt, args, out):
    measure = [sys.executable, os.path.join(ROOT, "harness", "measure.py"),
               "--path", c["path"], "--model", c["model"], "--prompt-id", c["prompt"],
               "--n", str(args.sentinel_n if c["sentinel"] else args.n), "--warmup", str(args.warmup),
               "--timeout", str(args.timeout), "--loss-pct", str(c["loss"]), "--delay-ms", str(c["delay"]),
               "--condition", f"{c['cell']}.{attempt}", "--run-id", args.run_id, "--out", os.path.join(out, "requests.csv")]
    if c["path"] == "loopback":
        measure += ["--host", "127.0.0.1"]
        return subprocess.run(measure).returncode
    cmd = ["sudo", "ip", "netns", "exec", "ue1", "sudo", "-u", getpass.getuser()] + measure
    return subprocess.run(cmd).returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--sentinel-n", type=int, default=20)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=30)
    ap.add_argument("--seed", type=int, default=20260917)
    ap.add_argument("--sentinel-every", type=int, default=10)
    ap.add_argument("--only", default=None, help="comma separated cell ids from an existing plan")
    args = ap.parse_args()

    out = os.path.join(ROOT, "data", args.run_id)
    os.makedirs(out, exist_ok=True)
    plan_path = os.path.join(out, "plan.json")
    if os.path.exists(plan_path):
        with open(plan_path) as f:
            plan = json.load(f)["cells"]
    else:
        plan = build_plan(args.seed, args.sentinel_every)
        with open(plan_path, "w") as f:
            json.dump({"seed": args.seed, "n": args.n, "sentinel_n": args.sentinel_n, "warmup": args.warmup,
                       "timeout_s": args.timeout, "cells": plan}, f, indent=1)
    if args.only:
        keep = set(args.only.split(","))
        plan = [c for c in plan if c["cell"] in keep]

    with open(os.path.join(out, f"manifest_{int(time.time())}.json"), "w") as f:
        subprocess.run([sys.executable, os.path.join(ROOT, "harness", "manifest.py")], stdout=f, check=False)
    sampler = subprocess.Popen([sys.executable, os.path.join(ROOT, "harness", "sampler.py"),
                                "--out", os.path.join(out, "system.csv")])
    events = os.path.join(out, "events.csv")

    try:
        for i, c in enumerate(plan):
            ev = [e for e in read_events(events) if e["cell"] == c["cell"]]
            if any(e["event"] in ("done", "gave_up") for e in ev):
                continue
            # rows from an interrupted attempt keep their own suffix and are never reused
            first = sum(e["event"] == "start" for e in ev) + 1
            for attempt in range(first, first + 3):
                impair.clear()
                if c["path"] == "ran" and not ran_healthy():
                    log_event(events, c["cell"], "ran_restart", f"attempt {attempt}")
                    restart_ran()
                    if not ran_healthy():
                        continue
                state = impair.apply(c["delay"], c["loss"]) if c["path"] == "ran" else impair.show()
                log_event(events, c["cell"], "start", json.dumps({k: c[k] for k in ("path", "model", "prompt", "loss", "delay", "sentinel")} | {"qdisc": state}))
                print(f"[{i + 1}/{len(plan)}] {c['cell']} {c['path']} {c['model']} {c['prompt']} loss={c['loss']} delay={c['delay']}", flush=True)
                ooms = oom_kills()
                run_cell(c, attempt, args, out)
                impair.clear()
                # an oom kill mid cell can drop a model or the ran and corrupt the cell
                if oom_kills() > ooms:
                    log_event(events, c["cell"], "oom_during", f"attempt {attempt}")
                    if c["path"] == "ran" and not ran_healthy():
                        restart_ran()
                    continue
                # a dead ran mid cell makes every request fail for reasons unrelated to the condition
                if c["path"] == "ran" and not ran_healthy():
                    log_event(events, c["cell"], "ran_down_after", f"attempt {attempt}")
                    restart_ran()
                    continue
                log_event(events, c["cell"], "done", f"attempt {attempt}")
                break
            else:
                log_event(events, c["cell"], "gave_up")
    finally:
        impair.clear()
        sampler.terminate()


if __name__ == "__main__":
    main()
