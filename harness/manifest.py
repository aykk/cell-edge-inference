#!/usr/bin/env python3
import json
import os
import platform
import subprocess
import sys
import time
import urllib.request

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.expanduser(os.environ.get("SRC", "~/src"))


def sh(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def cpu_model():
    with open("/proc/cpuinfo") as f:
        for line in f:
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return ""


def ollama(path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:11434{path}", timeout=5) as r:
            return json.load(r)
    except OSError:
        return None


def main():
    tags = ollama("/api/tags") or {}
    m = {
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "repo_sha": sh("git", "-C", REPO, "rev-parse", "HEAD"),
        "repo_dirty": bool(sh("git", "-C", REPO, "status", "--porcelain", "--untracked-files=no")),
        "srsran_project_sha": sh("git", "-C", f"{SRC}/srsRAN_Project", "rev-parse", "HEAD"),
        "srsran_4g_sha": sh("git", "-C", f"{SRC}/srsRAN_4G", "rev-parse", "HEAD"),
        "open5gs": sh("dpkg-query", "-W", "--showformat=${Version}", "open5gs"),
        "ollama": (ollama("/api/version") or {}).get("version"),
        "models": {t["name"]: t["digest"] for t in tags.get("models", [])},
        "kernel": platform.release(),
        "os": sh("lsb_release", "-ds"),
        "wsl": "microsoft" in platform.release().lower(),
        "cpu": cpu_model(),
        "nproc": os.cpu_count(),
        "mem_total_kb": int(open("/proc/meminfo").readline().split()[1]),
        "gpu": sh("/usr/lib/wsl/lib/nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"),
        "python": sys.version.split()[0],
        "qdisc_tun_srsue": sh("sudo", "ip", "netns", "exec", "ue1", "tc", "qdisc", "show", "dev", "tun_srsue"),
        "loadavg": open("/proc/loadavg").read().strip(),
    }
    json.dump(m, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
