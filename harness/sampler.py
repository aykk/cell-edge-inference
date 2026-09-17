#!/usr/bin/env python3
import argparse
import csv
import re
import subprocess
import threading
import time

NVSMI = "/usr/lib/wsl/lib/nvidia-smi"
FIELDS = ["wall", "loadavg_1m", "cpu_busy_pct", "rt_ratio_dl", "rt_ratio_ul",
          "gpu_temp_c", "gpu_util_pct", "gpu_mem_mib"]


def cpu_times():
    with open("/proc/stat") as f:
        v = list(map(int, f.readline().split()[1:]))
    idle = v[3] + v[4]
    return sum(v), idle


def zmq_bytes():
    # sport 2000 is gnb tx to ue and sport 2001 is ue tx to gnb
    out = subprocess.run(["ss", "-tin", "( sport = :2000 or sport = :2001 )"],
                         capture_output=True, text=True).stdout
    res = {}
    port = None
    for line in out.splitlines():
        m = re.search(r":(200[01])\s", line)
        if m:
            port = m.group(1)
            continue
        m = re.search(r"bytes_acked:(\d+)", line)
        if m and port:
            res[port] = res.get(port, 0) + int(m.group(1))
            port = None
    return res


class Gpu(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.last = ("", "", "")

    def run(self):
        try:
            p = subprocess.Popen([NVSMI, "--query-gpu=temperature.gpu,utilization.gpu,memory.used",
                                  "--format=csv,noheader,nounits", "-l", "1"],
                                 stdout=subprocess.PIPE, text=True)
        except OSError:
            return
        for line in p.stdout:
            parts = [x.strip() for x in line.split(",")]
            if len(parts) == 3:
                self.last = tuple(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--srate", type=float, default=23.04e6)
    ap.add_argument("--interval", type=float, default=1.0)
    args = ap.parse_args()

    gpu = Gpu()
    gpu.start()
    # zmq carries complex float32 samples at 8 bytes each
    realtime_bps = args.srate * 8
    prev_cpu, prev_z, prev_t = cpu_times(), zmq_bytes(), time.time()
    with open(args.out, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if f.tell() == 0:
            w.writeheader()
        while True:
            time.sleep(args.interval)
            cpu, z, t = cpu_times(), zmq_bytes(), time.time()
            dt = t - prev_t
            total, idle = cpu[0] - prev_cpu[0], cpu[1] - prev_cpu[1]

            def ratio(port):
                if port in z and port in prev_z and z[port] >= prev_z[port]:
                    return round((z[port] - prev_z[port]) / dt / realtime_bps, 4)
                return ""

            with open("/proc/loadavg") as la:
                load = la.read().split()[0]
            w.writerow({
                "wall": round(t, 3), "loadavg_1m": load,
                "cpu_busy_pct": round(100 * (total - idle) / total, 1) if total else "",
                "rt_ratio_dl": ratio("2000"), "rt_ratio_ul": ratio("2001"),
                "gpu_temp_c": gpu.last[0], "gpu_util_pct": gpu.last[1], "gpu_mem_mib": gpu.last[2],
            })
            f.flush()
            prev_cpu, prev_z, prev_t = cpu, z, t


if __name__ == "__main__":
    main()
