#!/usr/bin/env python3
"""The library's SQL Server (Tanmya Market, Db2BDoctorNew) -> IMED ERP, read-only, from the library's Windows PC.

Reads issued documents with the SELECTs in config.json (SELECT only; the app's procedures are never called, many of
them write), aliases the physical columns to the contract names the ERP expects (the names the Tanmya app itself
reads: TxtIdRefStock, TxtNumberRefStock, ...), and posts them in batches to
imed_erp.imederp.library_sync.sync.receive with Frappe token auth. Idempotent: the ERP keys every document on its
source id and skips an unchanged one, so running twice is harmless. The watermark (the last id acknowledged by
the ERP) is kept in state.json next to this file, and the last `reread_days` days are read again on every run so
a document held then issued, or issued then cancelled, is updated.

  python tanmya_connector.py --config config.json            one run (schedule it with Task Scheduler, every 10 min)
  python tanmya_connector.py --config config.json --dry-run  read and write batch_*.json, post nothing
  python tanmya_connector.py --config config.json --from-json batch.json   post a saved batch (tests)

Needs: Python 3.9+, pyodbc, requests, "ODBC Driver 17 for SQL Server" (or 18) on the PC.
"""
import argparse
import datetime as dt
import decimal
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state.json")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def jsonable(value):
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat(sep=" ") if isinstance(value, dt.datetime) else value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def rows_of(cursor):
    cols = [c[0] for c in cursor.description]
    return [{c: jsonable(v) for c, v in zip(cols, row)} for row in cursor.fetchall()]


def connect(cfg):
    import pyodbc  # imported here so --from-json works on a machine without the driver

    conn = pyodbc.connect(cfg["odbc"], autocommit=True, readonly=True)
    cur = conn.cursor()
    cur.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
    return conn


def read_family(conn, cfg, family, since_id, since_date):
    """One family (stock documents, cash receipts, cash payments): the heads newer than the watermark or dated in
    the re-read window, then their lines in one query, grouped under each head as `lines`."""
    q = cfg["queries"][family]
    cur = conn.cursor()
    cur.execute(q["heads"], (since_id, since_date))
    heads = rows_of(cur)
    if not heads:
        return []
    ids = [h[q["id_key"]] for h in heads]
    lines = []
    for i in range(0, len(ids), 500):
        chunk = ids[i : i + 500]
        cur.execute(q["lines"].replace("{ids}", ",".join("?" * len(chunk))), chunk)
        lines.extend(rows_of(cur))
    by_head = {}
    for line in lines:
        by_head.setdefault(line[q["line_head_key"]], []).append(line)
    for h in heads:
        h["lines"] = by_head.get(h[q["id_key"]], [])
        h["_family"] = family
    return heads


def post(cfg, batch):
    import requests

    url = cfg["erp"]["url"].rstrip("/") + "/api/method/imed_erp.imederp.library_sync.sync.receive"
    headers = {"Authorization": f"token {cfg['erp']['api_key']}:{cfg['erp']['api_secret']}", "Content-Type": "application/json"}
    r = requests.post(url, headers=headers, data=json.dumps({"batch": batch}, ensure_ascii=False).encode("utf-8"), timeout=120)
    r.raise_for_status()
    return r.json()["message"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "config.json"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--from-json")
    args = ap.parse_args()
    cfg = load(args.config)
    state = load(STATE) if os.path.exists(STATE) else {}

    if args.from_json:
        batch = load(args.from_json)
        print(post(cfg, batch))
        return

    conn = connect(cfg)
    since_date = (dt.date.today() - dt.timedelta(days=int(cfg.get("reread_days", 7)))).isoformat()
    documents = []
    for family in cfg["queries"]:
        documents += read_family(conn, cfg, family, int(state.get(family, 0)), since_date)
    conn.close()
    print(f"{dt.datetime.now():%Y-%m-%d %H:%M} read {len(documents)} documents")
    if not documents:
        return
    batch = {
        "source": cfg.get("source", "tanmya"),
        "branch_map": cfg.get("branch_map", {}),
        "operation_map": cfg.get("operation_map", {}),
        "issued_status_codes": cfg.get("issued_status_codes", []),
        "cancelled_status_codes": cfg.get("cancelled_status_codes", []),
        "read_at": dt.datetime.now().isoformat(sep=" "),
        "documents": documents,
    }
    if args.dry_run:
        out = os.path.join(HERE, f"batch_{dt.datetime.now():%Y%m%d_%H%M%S}.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(batch, f, ensure_ascii=False, indent=1)
        print("dry run: written", out)
        return
    size = int(cfg.get("batch_size", 200))
    for i in range(0, len(documents), size):
        part = dict(batch, documents=documents[i : i + size])
        for attempt in range(3):
            try:
                result = post(cfg, part)
                break
            except Exception as e:  # network or ERP down: retry, then leave the watermark where it was
                print("post failed:", e)
                time.sleep(10 * (attempt + 1))
        else:
            print("giving up this run; the next run reads these documents again")
            sys.exit(1)
        print("ERP:", result.get("log"), result.get("counts"))
        for family in cfg["queries"]:
            ids = [d[cfg["queries"][family]["id_key"]] for d in part["documents"] if d["_family"] == family]
            if ids:
                state[family] = max(int(state.get(family, 0)), max(int(x) for x in ids))
        with open(STATE, "w", encoding="utf-8") as f:
            json.dump(state, f)


if __name__ == "__main__":
    main()
