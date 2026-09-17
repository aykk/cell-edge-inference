#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL=${MODEL:-qwen2.5:0.5b}
PROMPT=${PROMPT:-short}
N=${N:-30}
DELAY=${DELAY:-100}
RUN_ID=${RUN_ID:-$(date +%Y%m%dT%H%M%S)}
OUT="$ROOT/data/$RUN_ID"
mkdir -p "$OUT"

IMPAIR="python3 $ROOT/harness/impair.py"
trap '$IMPAIR clear >/dev/null || true; kill $SAMPLER 2>/dev/null || true' EXIT

python3 "$ROOT/harness/manifest.py" > "$OUT/manifest.json"
python3 "$ROOT/harness/sampler.py" --out "$OUT/system.csv" &
SAMPLER=$!

measure() {
  sudo ip netns exec ue1 sudo -u "$USER" python3 "$ROOT/harness/measure.py" \
    --path ran --model "$MODEL" --prompt-id "$PROMPT" --n "$N" --run-id "$RUN_ID" \
    --condition "$1" --delay-ms "$2" --loss-pct 0 --out "$OUT/requests.csv"
}

ping_rtt() {
  sudo ip netns exec ue1 ping -q -c 10 -i 0.2 10.45.0.1 | tail -1
}

$IMPAIR clear > "$OUT/qdisc_before.json"
echo "before: $(ping_rtt)"
measure before 0

$IMPAIR apply --delay-ms "$DELAY" > "$OUT/qdisc_during.json"
cat "$OUT/qdisc_during.json"
echo "during: $(ping_rtt)"
measure during "$DELAY"

$IMPAIR clear > "$OUT/qdisc_after.json"
echo "after: $(ping_rtt)"
measure after 0

python3 "$ROOT/analysis/summarize.py" --by condition,delay_ms "$OUT/requests.csv"
