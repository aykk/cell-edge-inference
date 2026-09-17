#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

DBCTL=/tmp/open5gs-dbctl
[ -x "$DBCTL" ] || { curl -fsSL -o "$DBCTL" https://raw.githubusercontent.com/open5gs/open5gs/v2.8.0/misc/db/open5gs-dbctl; chmod +x "$DBCTL"; }

IMSI=001010123456780
KEY=00112233445566778899aabbccddeeff
OPC=63BFA50EE6523365FF14C1F45F88737D

# the amf needs sctp and wsl does not load the module on boot
echo sctp | sudo tee /etc/modules-load.d/sctp.conf >/dev/null
sudo modprobe sctp

for f in /etc/open5gs/amf.yaml /etc/open5gs/nrf.yaml; do
  sudo sed -i -E 's/^(\s+)mcc: 999$/\1mcc: 001/; s/^(\s+)mnc: 70$/\1mnc: 01/' "$f"
done
sudo sed -i -E 's/^(\s+)tac: 1$/\1tac: 7/' /etc/open5gs/amf.yaml

sudo systemctl restart open5gs-nrfd
sleep 2
sudo systemctl restart open5gs-scpd open5gs-amfd open5gs-smfd open5gs-upfd open5gs-ausfd open5gs-udmd open5gs-udrd open5gs-pcfd open5gs-nssfd open5gs-bsfd

if ! "$DBCTL" showfiltered | grep -q "$IMSI"; then
  "$DBCTL" add "$IMSI" "$KEY" "$OPC"
fi

sudo sysctl -w net.ipv4.ip_forward=1
sudo iptables -t nat -C POSTROUTING -s 10.45.0.0/16 ! -o ogstun -j MASQUERADE 2>/dev/null \
  || sudo iptables -t nat -A POSTROUTING -s 10.45.0.0/16 ! -o ogstun -j MASQUERADE
