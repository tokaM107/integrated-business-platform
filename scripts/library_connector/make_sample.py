"""Cuts a small sample out of the newest dry-run batch (batch_*.json next to this file), small enough to copy off the
library PC and to post as a first test (tanmya_connector.py --from-json sample.json): the 3 newest issued retail
sales, the newest retail return and the newest cancelled document, whichever exist. Writes sample.json."""
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

batches = sorted(glob.glob(os.path.join(HERE, "batch_*.json")))
if not batches:
    raise SystemExit("no batch_*.json here: run SETUP_CONNECTOR first")
with open(batches[-1], encoding="utf-8") as f:
    batch = json.load(f)
docs = sorted(batch["documents"], key=lambda d: int(d["TxtIdRefStock"]) if "TxtIdRefStock" in d else 0, reverse=True)


def pick(n, test):
    return [d for d in docs if test(d)][:n]


sample = (
    pick(3, lambda d: str(d.get("TxtOperationCodeRefStock")) == "18" and str(d.get("TxtStatusCodeRefStock")) == "11")
    + pick(1, lambda d: str(d.get("TxtOperationCodeRefStock")) == "19")
    + pick(1, lambda d: str(d.get("TxtStatusCodeRefStock")) == "13")
)
out = os.path.join(HERE, "sample.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(dict(batch, documents=sample), f, ensure_ascii=False, indent=1)
print(f"read {len(docs)} documents from {os.path.basename(batches[-1])}; wrote {len(sample)} to {out}")
