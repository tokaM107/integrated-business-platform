"""Compare two JSON count maps (imed_erp.setup.counts.run) and print 1 when equal, 0 otherwise; the table goes to stderr."""
import json
import sys

live, snap = json.loads(sys.argv[1]), json.loads(sys.argv[2])
same = 1
for k in live:
    flag = "same" if live[k] == snap.get(k) else "DIFFERENT"
    if flag != "same":
        same = 0
    print("  %-26s live %-8s snapshot %-8s %s" % (k, live[k], snap.get(k, "?"), flag), file=sys.stderr)
print(same)
