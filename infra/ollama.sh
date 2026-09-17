#!/usr/bin/env bash
set -euo pipefail
MODELS=${MODELS:-"qwen2.5:0.5b qwen2.5:1.5b qwen2.5:3b"}

command -v zstd >/dev/null || sudo apt-get install -y zstd
command -v ollama >/dev/null || curl -fsSL https://ollama.com/install.sh | sh

# the ue reaches ollama through ogstun so loopback only binding is not enough
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf >/dev/null <<'CONF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_KEEP_ALIVE=-1"
CONF
sudo systemctl daemon-reload
sudo systemctl restart ollama
for _ in $(seq 1 30); do curl -sf http://127.0.0.1:11434/api/version >/dev/null && break; sleep 1; done

for m in $MODELS; do ollama pull "$m"; done
ollama list
