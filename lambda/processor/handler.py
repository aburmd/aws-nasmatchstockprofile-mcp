# lambda/processor/handler.py
# Standardized inputs:
#   - CSV:    source/positions-YYYY-MM-DD.csv   (auto-pick latest if not provided)
#   - XLSX template: source/portfolio-template.xlsx
#   - XLSX output:   output/portfolio-updated-YYYYMMDD-HHMMSS.xlsx
#
# Behavior:
#   - Parse CSV by header (Account Name, Symbol, Quantity, Cost Basis Total / Average Cost Basis)
#   - Map CSV Account Name -> Excel header (row 1) via DDB overrides > Env map
#   - Write Qty to row 24, Cost to row 39 on each ticker sheet
#   - Emit run-report JSON and RunReport sheet for verification

import os
import io
import re
import json
import csv
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string

# ======== Env / Clients ========

BUCKET              = os.environ["BUCKET_NAME"]
MAPPING_TABLE_NAME  = os.environ.get("MAPPING_TABLE")  # optional
DEFAULT_DATASET_ID  = os.environ.get("DEFAULT_DATASET_ID", "default")
SOURCE_PREFIX       = os.environ.get("SOURCE_PREFIX", "source/")
OUTPUT_PREFIX       = os.environ.get("OUTPUT_PREFIX", "output/")
DEFAULT_CSV_PREFIX  = os.environ.get("DEFAULT_CSV_PREFIX", "positions-")  # NEW
TEMPLATE_KEY        = os.environ.get("TEMPLATE_KEY", "source/portfolio-template.xlsx")  # NEW

ROW_QTY  = int(os.environ.get("ROW_QTY", "24"))   # Total Buy Qty
ROW_COST = int(os.environ.get("ROW_COST", "39"))  # Buy Shunks
COST_MODE = os.environ.get("COST_MODE", "total_basis").lower()  # 'total_basis' | 'avg_per_share'

# Optional inline mapping in env (CSV Account Name -> Excel header cell in row 1)
try:
    ENV_MAP = json.loads(os.environ.get("ACCOUNT_NAME_MAP_JSON", "{}") or "{}")
except Exception:
    ENV_MAP = {}

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb") if MAPPING_TABLE_NAME else None
mapping_table = dynamodb.Table(MAPPING_TABLE_NAME) if dynamodb and MAPPING_TABLE_NAME else None


# ======== Utils ========

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")

def _ts_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

def _to_money(s):
    if s is None:
        return 0.0
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).replace(",", "").strip()
    s = re.sub(r"[^\d\.\-\+]", "", s)
    try:
        return float(s) if s else 0.0
    except Exception:
        return 0.0

def _to_float(s):
    if s is None:
        return 0.0
    try:
        return float(str(s).replace(",", "").strip())
    except Exception:
        return 0.0

def _norm_header(h: str) -> str:
    """
    Normalize headers and account names for matching:
      - lowercase, strip, collapse spaces
      - unify '401 k' -> '401k'
    """
    if not h:
        return ""
    s = str(h).strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("401 k", "401k")
    return s

def _get_obj_bytes(bucket: str, key: str) -> bytes:
    resp = s3.get_object(Bucket=bucket, Key=key)
    return resp["Body"].read()

def _put_obj_bytes(bucket: str, key: str, body: bytes, content_type: str):
    s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)

def _load_workbook_from_s3(key: str):
    data = _get_obj_bytes(BUCKET, key)
    bio = io.BytesIO(data)
    return load_workbook(bio)

def _save_json_report(bucket, key, payload: dict):
    _put_obj_bytes(bucket, key, json.dumps(payload, indent=2).encode("utf-8"), "application/json")
    print(f"[REPORT] s3://{bucket}/{key}")

def _symbol_from_sheetname(name: str) -> str:
    # e.g., "AVGO(AT1)" -> "AVGO"
    return re.split(r"[\s\(\-:]+", str(name).strip(), 1)[0].upper()

def _list_keys(prefix: str) -> list:
    keys = []
    cont = None
    while True:
        if cont:
            resp = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix, ContinuationToken=cont)
        else:
            resp = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix)
        for it in resp.get("Contents", []):
            keys.append(it["Key"])
        cont = resp.get("NextContinuationToken")
        if not cont:
            break
    return keys

def _latest_by_prefix(prefix: str, suffix: str | None = None) -> str | None:
    keys = _list_keys(prefix)
    if suffix:
        keys = [k for k in keys if k.endswith(suffix)]
    if not keys:
        return None
    keys.sort()  # lexicographic ok with YYYY-MM-DD
    return keys[-1]


# ======== CSV Reader (header-based) ========

CSV_COLS = {
    "account_name": "Account Name",
    "symbol":       "Symbol",
    "quantity":     "Quantity",
    "cost_total":   "Cost Basis Total",
    "cost_avg":     "Average Cost Basis",
}

def _read_positions_csv(csv_bytes: bytes) -> List[dict]:
    rdr = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
    rows = []
    missing = [c for c in CSV_COLS.values() if c not in (rdr.fieldnames or [])]
    if missing:
        print(f"[WARN] Missing expected columns: {missing} (proceeding with what exists)")
    for r in rdr:
        acct = (r.get(CSV_COLS["account_name"]) or "").strip()
        sym  = (r.get(CSV_COLS["symbol"]) or "").strip().upper()
        if not acct or not sym:
            continue
        qty  = _to_float(r.get(CSV_COLS["quantity"]))
        if COST_MODE == "avg_per_share":
            cost = _to_money(r.get(CSV_COLS["cost_avg"]))
        else:
            cost = _to_money(r.get(CSV_COLS["cost_total"]))
        rows.append({"account_name": acct, "symbol": sym, "qty": qty, "cost": cost})
    print(f"[PARSE] rows={len(rows)} COST_MODE={COST_MODE}")
    return rows


# ======== Mapping (CSV Account -> Excel Header) ========

def _load_env_map() -> Dict[str, str]:
    return { _norm_header(k): v for k, v in (ENV_MAP or {}).items() }

def _load_ddb_map(dataset_id: str) -> Dict[str, str]:
    if not mapping_table:
        return {}
    out = {}
    try:
        resp = mapping_table.query(KeyConditionExpression=Key("dataset_id").eq(dataset_id))
        for item in resp.get("Items", []):
            src = _norm_header(item.get("source_col"))
            tgt = item.get("target_col")
            if src and tgt:
                out[src] = tgt
        while "LastEvaluatedKey" in resp:
            resp = mapping_table.query(
                KeyConditionExpression=Key("dataset_id").eq(dataset_id),
                ExclusiveStartKey=resp["LastEvaluatedKey"]
            )
            for item in resp.get("Items", []):
                src = _norm_header(item.get("source_col"))
                tgt = item.get("target_col")
                if src and tgt:
                    out[src] = tgt
    except ClientError as e:
        print(f"[WARN] DDB query failed: {e}")
    return out

def _resolve_target_header(csv_account: str, ddb_map: Dict[str, str], env_map: Dict[str, str]) -> str | None:
    n = _norm_header(csv_account)
    if n in ddb_map:
        return ddb_map[n]
    return env_map.get(n)


# ======== Aggregate & Write ========

def _sheet_headers(ws) -> Dict[str, int]:
    hdrs = {}
    for cell in ws[1]:
        # only from column B onward
        if cell.column < column_index_from_string("B"):
            continue
        val = cell.value
        if val is None:
            continue
        hdrs[_norm_header(str(val))] = cell.column
    return hdrs

def _aggregate_by_symbol_account(rows: List[dict], ddb_map: Dict[str, str], env_map: Dict[str, str]) -> Dict[str, Dict[str, dict]]:
    out: Dict[str, Dict[str, dict]] = {}
    for r in rows:
        tgt = _resolve_target_header(r["account_name"], ddb_map, env_map)
        if not tgt:
            out.setdefault("_unmapped", {}).setdefault(r["account_name"], 0)
            out["_unmapped"][r["account_name"]] += 1
            continue
        smap = out.setdefault(r["symbol"], {})
        cell = smap.setdefault(tgt, {"qty": 0.0, "cost": 0.0})
        cell["qty"]  += r["qty"]
        cell["cost"] += r["cost"]
    return out

def _write_per_ticker(wb, agg: Dict[str, Dict[str, dict]]) -> Tuple[int, dict, dict, dict]:
    updated = 0
    headers_by_sheet = {}
    missing_accounts = {}
    writes_detail = {}

    for ws in wb.worksheets:
        sym = _symbol_from_sheetname(ws.title)
        if sym not in agg:
            continue

        hdr_map = _sheet_headers(ws)
        headers_by_sheet[sym] = {
            "raw": [str(c.value) for c in ws[1]],
            "normalized": list(hdr_map.keys())
        }

        for target_header, sums in agg[sym].items():
            col = hdr_map.get(_norm_header(target_header))
            if not col:
                missing_accounts.setdefault(sym, []).append(target_header)
                continue

            ws.cell(row=ROW_QTY,  column=col, value=sums["qty"])
            ws.cell(row=ROW_COST, column=col, value=sums["cost"])
            updated += 1

            sd = writes_detail.setdefault(sym, {})
            sd[target_header] = {"qty_written": sums["qty"], "cost_written": sums["cost"]}

    return updated, headers_by_sheet, missing_accounts, writes_detail


# ======== Reporting ========

def _build_report(parsed_rows: List[dict], agg: dict, headers_by_sheet: dict, writes_detail: dict, missing_accounts: dict):
    symbols_updated = sorted(list(writes_detail.keys()))
    total_writes = sum(len(v) for v in writes_detail.values())
    csv_accounts_seen = sorted(set(r["account_name"] for r in parsed_rows))
    return {
        "timestamp": _ts(),
        "summary": {
            "csv_rows_parsed": len(parsed_rows),
            "symbols_updated_count": len(symbols_updated),
            "per_ticker_writes": total_writes
        },
        "csv_accounts_seen": csv_accounts_seen,
        "symbols_updated": symbols_updated,
        "headers_by_sheet": headers_by_sheet,
        "missing_accounts": missing_accounts,
        "writes_detail": writes_detail
    }

def _write_runreport_sheet(wb, report, src_key, tgt_key, out_key):
    wsname = "RunReport"
    if wsname in wb.sheetnames:
        ws = wb[wsname]
        ws.delete_rows(1, ws.max_row)
    else:
        ws = wb.create_sheet(wsname, 0)

    rows = [
        ["RunReport generated (UTC)", report["timestamp"]],
        ["Source CSV", src_key],
        ["Template XLSX", tgt_key],
        ["Output Excel", out_key],
        ["CSV Rows Parsed", report["summary"]["csv_rows_parsed"]],
        ["Symbols Updated", report["summary"]["symbols_updated_count"]],
        ["Per-ticker Writes", report["summary"]["per_ticker_writes"]],
        [],
        ["Symbol", "Account Header", "Qty Written", "Cost Written"]
    ]
    for sym in report["symbols_updated"]:
        for acct, vals in (report["writes_detail"].get(sym) or {}).items():
            rows.append([sym, acct, vals.get("qty_written", 0), vals.get("cost_written", 0)])

    rows.append([])
    rows.append(["Sheet(Symbol)", "Headers (raw row1) / normalized"])
    for sym, hdrs in (report.get("headers_by_sheet") or {}).items():
        rows.append([sym, ", ".join(hdrs.get("raw") or [])])
        rows.append(["",   ", ".join(hdrs.get("normalized") or [])])

    rows.append([])
    rows.append(["Symbol", "Missing account headers (not found in row 1)"])
    for sym, miss in (report.get("missing_accounts") or {}).items():
        rows.append([sym, ", ".join(miss)])

    for r in rows:
        ws.append(r)
    ws.freeze_panes = "A9"


# ======== Main ========

def main(event, context):
    # Allow explicit keys in event
    source_key = (event or {}).get("source_key")
    target_key = (event or {}).get("target_key")
    output_key = (event or {}).get("output_key")

    # Default CSV: latest source/positions-*.csv
    if not source_key:
        latest_csv = _latest_by_prefix(SOURCE_PREFIX + DEFAULT_CSV_PREFIX, ".csv")
        if not latest_csv:
            return {"status": "error", "message": f"No CSV found under {SOURCE_PREFIX}{DEFAULT_CSV_PREFIX}*.csv"}
        source_key = latest_csv

    # Default template
    if not target_key:
        target_key = TEMPLATE_KEY

    # Default output (timestamped)
    if not output_key:
        output_key = f"{OUTPUT_PREFIX.rstrip('/')}/portfolio-updated-{_ts_compact()}.xlsx"

    # 1) Load CSV + Template
    csv_bytes = _get_obj_bytes(BUCKET, source_key)
    rows = _read_positions_csv(csv_bytes)
    wb = _load_workbook_from_s3(target_key)

    # 2) Build mapping
    ddb_map = _load_ddb_map(DEFAULT_DATASET_ID)
    env_map = _load_env_map()
    agg = _aggregate_by_symbol_account(rows, ddb_map, env_map)

    # 3) Write into workbook
    updated, headers_by_sheet, missing_accounts, writes_detail = _write_per_ticker(wb, agg)

    # 4) Report
    ts = _ts_compact()
    report_key = f"{OUTPUT_PREFIX.rstrip('/')}/reports/{ts}-report.json"
    report = _build_report(rows, agg, headers_by_sheet, writes_detail, missing_accounts)
    _write_runreport_sheet(wb, report, source_key, target_key, output_key)
    _save_json_report(BUCKET, report_key, report)

    # 5) Save workbook
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    _put_obj_bytes(BUCKET, output_key, buf.read(),
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    return {
        "status": "ok",
        "bucket": BUCKET,
        "source_key": source_key,
        "target_key": target_key,
        "output_key": output_key,
        "report_key": report_key,
        "wrote_rows": len(rows),
        "per_ticker_writes": updated,
        "symbols_updated": sorted(list(writes_detail.keys())),
        "missing_accounts": missing_accounts
    }
