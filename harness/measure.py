#!/usr/bin/env python3
import argparse
import csv
import http.client
import json
import os
import socket
import sys
import time
import uuid

FIELDS = [
    "run_id", "request_id", "seq", "warmup", "path", "model", "prompt_id",
    "loss_pct", "delay_ms", "condition", "wall_start", "wall_end",
    "ttft_ms", "total_ms", "connect_ms", "headers_ms",
    "tokens", "eval_count", "tokens_per_s", "ok", "failure", "detail",
    "loadavg_1m", "prompt_nonce",
]

# ttft: request dispatch to arrival of the first chunk with non-empty response text
# total: request dispatch to arrival of the chunk marked done
# dispatch is taken just before the tcp connect so connection setup counts toward both
# failures: timeout, conn_error, http_error, malformed, incomplete


def one_request(host, port, model, prompt, num_predict, timeout_s):
    row = {"ttft_ms": "", "total_ms": "", "connect_ms": "", "headers_ms": "",
           "tokens": 0, "eval_count": "", "tokens_per_s": "",
           "ok": 0, "failure": "", "detail": ""}
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {"temperature": 0, "seed": 42, "num_predict": num_predict},
    })
    deadline = None
    t0 = time.perf_counter()
    t_first = None
    conn = http.client.HTTPConnection(host, port, timeout=timeout_s)
    try:
        conn.connect()
        row["connect_ms"] = round((time.perf_counter() - t0) * 1000, 3)
        deadline = t0 + timeout_s
        conn.request("POST", "/api/generate", body, {"Content-Type": "application/json"})
        resp = conn.getresponse()
        row["headers_ms"] = round((time.perf_counter() - t0) * 1000, 3)
        if resp.status != 200:
            row["failure"], row["detail"] = "http_error", str(resp.status)
            return row
        while True:
            if time.perf_counter() > deadline:
                row["failure"], row["detail"] = "timeout", "total deadline"
                return row
            line = resp.readline()
            if not line:
                row["failure"] = "incomplete"
                return row
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                row["failure"], row["detail"] = "malformed", line[:80].decode(errors="replace")
                return row
            now = time.perf_counter()
            if "error" in msg:
                row["failure"], row["detail"] = "http_error", str(msg["error"])[:80]
                return row
            if msg.get("response"):
                row["tokens"] += 1
                if t_first is None:
                    t_first = now
                    row["ttft_ms"] = round((now - t0) * 1000, 3)
            if msg.get("done"):
                row["total_ms"] = round((now - t0) * 1000, 3)
                row["eval_count"] = msg.get("eval_count", "")
                if t_first is not None and now > t_first and row["tokens"] > 1:
                    row["tokens_per_s"] = round((row["tokens"] - 1) / (now - t_first), 3)
                row["ok"] = 1
                return row
    except socket.timeout as e:
        row["failure"], row["detail"] = "timeout", str(e)[:80]
    except (ConnectionError, OSError, http.client.HTTPException) as e:
        row["failure"], row["detail"] = "conn_error", f"{type(e).__name__}: {e}"[:80]
    finally:
        conn.close()
    return row


def loadavg():
    try:
        with open("/proc/loadavg") as f:
            return f.read().split()[0]
    except OSError:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="10.45.0.1")
    ap.add_argument("--port", type=int, default=11434)
    ap.add_argument("--path", default="ran", help="ran or loopback")
    ap.add_argument("--model", required=True)
    ap.add_argument("--prompts", default=os.path.join(os.path.dirname(__file__), "..", "experiments", "prompts.json"))
    ap.add_argument("--prompt-id", required=True)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--num-predict", type=int, default=128)
    ap.add_argument("--timeout", type=float, default=60)
    ap.add_argument("--gap", type=float, default=0.5, help="seconds between requests")
    ap.add_argument("--loss-pct", default="0")
    ap.add_argument("--delay-ms", default="0")
    ap.add_argument("--condition", default="baseline")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-nonce", action="store_true")
    args = ap.parse_args()

    with open(args.prompts) as f:
        prompt = json.load(f)[args.prompt_id]
    run_id = args.run_id or time.strftime("%Y%m%dT%H%M%S")
    new_file = not os.path.exists(args.out) or os.path.getsize(args.out) == 0
    with open(args.out, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for seq in range(args.warmup + args.n):
            # a unique first line defeats ollama prompt caching so every request pays full prefill
            nonce = "" if args.no_nonce else uuid.uuid4().hex[:8]
            text = f"Request {nonce}.\n{prompt}" if nonce else prompt
            wall_start = time.time()
            r = one_request(args.host, args.port, args.model, text, args.num_predict, args.timeout)
            r.update({
                "run_id": run_id, "request_id": uuid.uuid4().hex[:12], "seq": seq,
                "warmup": int(seq < args.warmup), "path": args.path, "model": args.model,
                "prompt_id": args.prompt_id, "loss_pct": args.loss_pct, "delay_ms": args.delay_ms,
                "condition": args.condition, "wall_start": round(wall_start, 6),
                "wall_end": round(time.time(), 6), "loadavg_1m": loadavg(), "prompt_nonce": nonce,
            })
            w.writerow(r)
            f.flush()
            if not r["ok"]:
                print(f"seq {seq} {r['failure']} {r['detail']}", file=sys.stderr)
            time.sleep(args.gap)


if __name__ == "__main__":
    main()
