#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL=${MODEL:-qwen2.5:0.5b}
PROMPT=${PROMPT:-short}
N=${N:-100}
RUN_ID=${RUN_ID:-$(date +%Y%m%dT%H%M%S)}
OUT="$ROOT/data/$RUN_ID"
mkdir -p "$OUT"

python3 "$ROOT/harness/manifest.py" > "$OUT/manifest.json"
python3 "$ROOT/harness/sampler.py" --out "$OUT/system.csv" &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null || true' EXIT

# run as the invoking user inside the ue namespace so files stay user owned
sudo ip netns exec ue1 sudo -u "$USER" python3 "$ROOT/harness/measure.py" \
  --path ran --model "$MODEL" --prompt-id "$PROMPT" --n "$N" \
  --run-id "$RUN_ID" --out "$OUT/requests.csv"

python3 "$ROOT/analysis/summarize.py" "$OUT/requests.csv"
