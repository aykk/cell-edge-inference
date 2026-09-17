#!/usr/bin/env python3
import re
import sys
from datetime import datetime

# 15 khz scs means 10 slots per frame and 10 ms per frame
SLOTS_PER_FRAME = 10
SLOT_S = 0.001

pat = re.compile(r"^(\S+) \[\w+\s*\] \[\w\] \[\s*(\d+)\.(\d+)\]")
pts = []
for line in open(sys.argv[1], errors="replace"):
    m = pat.match(line)
    if m:
        t = datetime.fromisoformat(m.group(1)).timestamp()
        pts.append((t, int(m.group(2)) * SLOTS_PER_FRAME + int(m.group(3))))
if len(pts) < 2:
    sys.exit("no slot-stamped lines")

wall = sim = 0.0
for (t0, s0), (t1, s1) in zip(pts, pts[1:]):
    ds = (s1 - s0) % (1024 * SLOTS_PER_FRAME)
    # skip gaps longer than half an sfn cycle where wraparound is ambiguous
    if t1 - t0 > 5:
        continue
    wall += t1 - t0
    sim += ds * SLOT_S
print(f"lines={len(pts)} wall={wall:.2f}s sim={sim:.2f}s ratio={sim / wall:.3f}")
