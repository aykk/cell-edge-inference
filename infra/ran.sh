#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC=${SRC:-$HOME/src}
GNB_CFG=${GNB_CFG:-$HERE/gnb.yaml}
UE_CFG=${UE_CFG:-$HERE/ue.conf}

stop() {
  sudo pkill -x srsue || true
  sudo pkill -x gnb || true
  for _ in $(seq 1 20); do pgrep -x 'srsue|gnb' >/dev/null || return 0; sleep 0.5; done
  sudo pkill -9 -x srsue || true
  sudo pkill -9 -x gnb || true
}

start() {
  stop
  # gnb first deadlocks the zmq handshake
  sudo ip netns list | grep -qw ue1 || sudo ip netns add ue1
  sudo sh -c "nohup $SRC/srsRAN_4G/build/srsue/src/srsue $UE_CFG > /tmp/ue.out 2>&1 < /dev/null &"
  for _ in $(seq 1 60); do grep -q 'PHY to initialize ... done' /tmp/ue.out 2>/dev/null && break; sleep 1; done
  sudo sh -c "nohup $SRC/srsRAN_Project/build/apps/gnb/gnb -c $GNB_CFG > /tmp/gnb.out 2>&1 < /dev/null &"
  for _ in $(seq 1 180); do
    if grep -q 'PDU Session Establishment successful' /tmp/ue.out; then
      sudo ip netns exec ue1 ip route replace default via 10.45.0.1 dev tun_srsue
      grep 'PDU Session' /tmp/ue.out
      return 0
    fi
    sleep 1
  done
  echo "ue did not attach" >&2
  tail -5 /tmp/ue.out >&2
  return 1
}

"${1:-start}"
