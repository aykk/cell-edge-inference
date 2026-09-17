#!/usr/bin/env bash
set -euo pipefail
SRATE=${1:?usage: zmqrate.sh base_srate_hz [seconds]}
SECS=${2:-10}
f() { ss -tin '( sport = :2000 or sport = :2001 )' | grep -oE 'bytes_acked:[0-9]+' | cut -d: -f2 | paste -sd' '; }
a=$(f); t0=$(date +%s.%N); sleep "$SECS"; b=$(f); t1=$(date +%s.%N)
python3 - "$SRATE" "$t0" "$t1" "$a" "$b" <<'PY'
import sys
srate, t0, t1 = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
a, b = map(int, sys.argv[4].split()), map(int, sys.argv[5].split())
# zmq carries complex float32 samples at 8 bytes each
for x, y in zip(a, b):
    print(f"{(y - x) / (t1 - t0) / (srate * 8):.3f}")
PY
