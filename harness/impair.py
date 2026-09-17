#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys

NS = "ue1"
DEV = "tun_srsue"
IFB = "ifb_ue"

# delay_ms and loss_pct apply to each direction independently
# uplink uses netem on the tun egress and downlink is redirected through an ifb with its own netem


def ns(*cmd, check=True):
    r = subprocess.run(["sudo", "ip", "netns", "exec", NS, *cmd], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}: {r.stderr.strip()}")
    return r


def netem_args(delay_ms, loss_pct):
    args = ["netem"]
    if float(delay_ms) > 0:
        args += ["delay", f"{delay_ms}ms"]
    if float(loss_pct) > 0:
        args += ["loss", f"{loss_pct}%"]
    return args


def clear():
    ns("tc", "qdisc", "del", "dev", DEV, "root", check=False)
    ns("tc", "qdisc", "del", "dev", DEV, "ingress", check=False)
    ns("ip", "link", "del", IFB, check=False)
    state = show()
    if state["netem"] or state["ingress"] or state["ifb"]:
        raise RuntimeError(f"impairment still present after clear: {state}")
    return state


def apply(delay_ms, loss_pct):
    clear()
    if float(delay_ms) == 0 and float(loss_pct) == 0:
        return show()
    ns("ip", "link", "add", IFB, "type", "ifb")
    ns("ip", "link", "set", IFB, "up")
    ns("tc", "qdisc", "add", "dev", DEV, "root", *netem_args(delay_ms, loss_pct))
    ns("tc", "qdisc", "add", "dev", DEV, "handle", "ffff:", "ingress")
    ns("tc", "filter", "add", "dev", DEV, "parent", "ffff:", "matchall",
       "action", "mirred", "egress", "redirect", "dev", IFB)
    ns("tc", "qdisc", "add", "dev", IFB, "root", *netem_args(delay_ms, loss_pct))
    verify(delay_ms, loss_pct)
    return show()


def parse_netem(text):
    m = re.search(r"qdisc netem .*", text)
    if not m:
        return None
    line = m.group(0)
    d = re.search(r"delay ([\d.]+)(us|ms|s)\b", line)
    l = re.search(r"loss ([\d.]+)%", line)
    scale = {"us": 0.001, "ms": 1, "s": 1000}
    return {
        "delay_ms": float(d.group(1)) * scale[d.group(2)] if d else 0.0,
        "loss_pct": float(l.group(1)) if l else 0.0,
        "raw": line.strip(),
    }


def show():
    up = ns("tc", "qdisc", "show", "dev", DEV).stdout
    ifb_link = ns("ip", "link", "show", IFB, check=False)
    down = ns("tc", "qdisc", "show", "dev", IFB).stdout if ifb_link.returncode == 0 else ""
    filters = ns("tc", "filter", "show", "dev", DEV, "parent", "ffff:", check=False).stdout
    return {
        "netem": bool(parse_netem(up) or parse_netem(down)),
        "uplink": parse_netem(up),
        "downlink": parse_netem(down),
        "ingress": "qdisc ingress" in up,
        "redirect": "mirred" in filters,
        "ifb": ifb_link.returncode == 0,
    }


def verify(delay_ms, loss_pct):
    s = show()
    want = {"delay_ms": float(delay_ms), "loss_pct": float(loss_pct)}
    for side in ("uplink", "downlink"):
        got = s[side]
        if got is None or abs(got["delay_ms"] - want["delay_ms"]) > 1e-6 or abs(got["loss_pct"] - want["loss_pct"]) > 1e-6:
            raise RuntimeError(f"{side} netem mismatch want {want} got {got}")
    if not s["redirect"]:
        raise RuntimeError("downlink redirect to ifb missing")
    return s


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("apply")
    a.add_argument("--delay-ms", default="0")
    a.add_argument("--loss-pct", default="0")
    sub.add_parser("clear")
    sub.add_parser("show")
    args = ap.parse_args()
    try:
        if args.cmd == "apply":
            out = apply(args.delay_ms, args.loss_pct)
        elif args.cmd == "clear":
            out = clear()
        else:
            out = show()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    print(json.dumps(out))


if __name__ == "__main__":
    main()
