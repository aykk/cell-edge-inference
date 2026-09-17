#!/usr/bin/env bash
set -euo pipefail

SRSRAN_PROJECT_REF=release_25_10
SRSRAN_4G_REF=release_25_10
SRC=${SRC:-$HOME/src}
JOBS=${JOBS:-4}

export DEBIAN_FRONTEND=noninteractive
sudo apt-get update
sudo apt-get install -y software-properties-common ca-certificates curl gnupg git \
  build-essential cmake make gcc g++ pkg-config \
  libfftw3-dev libmbedtls-dev libsctp-dev libyaml-cpp-dev libgtest-dev \
  libzmq3-dev libboost-program-options-dev libconfig++-dev \
  iproute2 iptables tcpdump python3-venv

if ! command -v mongod >/dev/null; then
  curl -fsSL https://pgp.mongodb.com/server-8.0.asc | sudo gpg --yes -o /usr/share/keyrings/mongodb-server-8.0.gpg --dearmor
  echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg ] https://repo.mongodb.org/apt/ubuntu noble/mongodb-org/8.0 multiverse" \
    | sudo tee /etc/apt/sources.list.d/mongodb-org-8.0.list
  sudo apt-get update
  sudo apt-get install -y mongodb-org
fi
sudo systemctl enable --now mongod

sudo add-apt-repository -y ppa:open5gs/latest
sudo apt-get update
sudo apt-get install -y open5gs

mkdir -p "$SRC"

if [ ! -d "$SRC/srsRAN_Project" ]; then
  git clone --depth 1 --branch "$SRSRAN_PROJECT_REF" https://github.com/srsran/srsRAN_Project "$SRC/srsRAN_Project"
fi
cmake -S "$SRC/srsRAN_Project" -B "$SRC/srsRAN_Project/build" -DCMAKE_BUILD_TYPE=Release -DENABLE_EXPORT=ON -DENABLE_ZEROMQ=ON -DAUTO_DETECT_ISA=ON
make -C "$SRC/srsRAN_Project/build" -j"$JOBS" gnb

if [ ! -d "$SRC/srsRAN_4G" ]; then
  git clone --depth 1 --branch "$SRSRAN_4G_REF" https://github.com/srsran/srsRAN_4G "$SRC/srsRAN_4G"
fi
cmake -S "$SRC/srsRAN_4G" -B "$SRC/srsRAN_4G/build" -DCMAKE_BUILD_TYPE=Release
make -C "$SRC/srsRAN_4G/build" -j"$JOBS" srsue

echo install done
