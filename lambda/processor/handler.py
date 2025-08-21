import os
import io
import csv
import json
import boto3
from botocore.client import Config
from decimal import Decimal, InvalidOperation
from openpyxl import load_workbook, Workbook

s3 = boto3.client("s3", config=Config(signature_version="s3v4"))

BUCKET = os.environ["BUCKET_NAME"]
MAPPING_TABLE = os.environ.get("MAPPING_TABLE")  # not used in this step
SOURCE_PREFIX = os.environ.get("SOURCE_PREFIX", "source/")
OUTPUT_PREFIX = os.environ.get("OUTPUT_PREFIX", "output/")

# Expected consolidate headers in the template (and their CSV sources)
CONSOLIDATE_HEADERS = [
    "Account Number",
    "Account Name",
    "Symbol",
    "Quantity",
    "Cost Basis Total",
    "Average Cost Basis",
    "Type",
]

# CSV column names we’ll map from (case-sensitive from your sample)
CSV_COLS = {
    "account_number": "Account Number",
    "account_name": "Account Name",
    "symbol": "Symbol",
    "quantity": "Quantity",
    "cost_total": "Cost Basis Total",
    "avg_cost": "Average Cost Basis",
    "type": "Type",
}

def _get_obj_bytes(bucket: str, key: str) -> bytes:
    resp = s3.get_object(Bucket=bucket, Key=key)
    return resp["Body"].read()

def _put_obj_bytes(bucket: str, key: str, body: bytes, content_type: str):
    s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)

def _clean_money(s: str):
    """
    Convert money-like strings to Decimal:
    "$1,234.56" -> Decimal("1234.56")
    "-" or "" or None -> None
    """
    if s is None:
        return None
    if isinstance(s, (int, float, Decimal)):
        try:
            return Decimal(str(s))
        except InvalidOperation:
            return None
    s = str(s).strip()
    if not s or s.upper() == "NAN" or s == "-":
        return None
    # remove $ , and parentheses for negatives
    s = s.replace("$", "").replace(",", "")
    s = s.replace("(", "-").replace(")", "")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None

def _clean_number(s: str):
    """
    Convert numeric-like strings to Decimal (for quantity):
    "1,234.56" -> Decimal("1234.56")
    """
    if s is None:
        return None
    if isinstance(s, (int, float, Decimal)):
        try:
            return Decimal(str(s))
        except InvalidOperation:
            return None
    s = str(s).strip()
    if not s or s.upper() == "NAN" or s == "-":
        return None
    s = s.replace(",", "")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None

def _read_positions_csv(csv_bytes: bytes):
    """
    Reads the Fidelity positions CSV based on your attached file’s headers.
    Returns a list of dicts aligned to CONSOLIDATE_HEADERS.
    """
    rows = []
    text = csv_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    for r in reader:
        # Skip the cash row with no symbol qty? (We’ll still allow it to pass through if present)
        account_number = r.get(CSV_COLS["account_number"])
        account_name = r.get(CSV_COLS["account_name"])
        symbol = r.get(CSV_COLS["symbol"])
        qty = _clean_number(r.get(CSV_COLS["quantity"]))
        cost_total = _clean_money(r.get(CSV_COLS["cost_total"]))
        avg_cost = _clean_money(r.get(CSV_COLS["avg_cost"]))
        sec_type = r.get(CSV_COLS["type"])

        # Build clean row as basic Python types for openpyxl
        rows.append({
            "Account Number": int(account_number) if account_number and account_number.isdigit() else account_number,
            "Account Name": account_name,
            "Symbol": symbol,
            "Quantity": float(qty) if qty is not None else None,
            "Cost Basis Total": float(cost_total) if cost_total is not None else None,
            "Average Cost Basis": float(avg_cost) if avg_cost is not None else None,
            "Type": sec_type,
        })
    return rows

def _ensure_consolidate_sheet(wb):
    """
    Ensure 'consolidate' exists with headers; return the worksheet.
    """
    if "consolidate" in wb.sheetnames:
        ws = wb["consolidate"]
    else:
        ws = wb.create_sheet("consolidate")

    # Write headers in row 1 exactly as required
    for idx, h in enumerate(CONSOLIDATE_HEADERS, start=1):
        ws.cell(row=1, column=idx, value=h)
    return ws

def _write_consolidate(ws, rows):
    """
    Overwrite any existing data (from row 2 down) and write fresh rows.
    """
    # Clear existing rows (except header)
    max_row = ws.max_row
    if max_row > 1:
        ws.delete_rows(idx=2, amount=max_row - 1)

    # Write new data
    r = 2
    for item in rows:
        for c_idx, h in enumerate(CONSOLIDATE_HEADERS, start=1):
            ws.cell(row=r, column=c_idx, value=item.get(h))
        r += 1

def _load_workbook_from_s3(key: str):
    try:
        xbytes = _get_obj_bytes(BUCKET, key)
        return load_workbook(io.BytesIO(xbytes))
    except s3.exceptions.NoSuchKey:
        # Create a fresh workbook if the target doesn't exist
        return Workbook()

def main(event, context):
    """
    Supports:
    1) Direct JSON (manual invoke)
    2) S3 Event (auto on upload to source/*.csv)
    """
    print("Event:", json.dumps(event))

    # Case 2: S3 event
    if isinstance(event, dict) and "Records" in event and event["Records"]:
        rec = event["Records"][0]
        s3info = rec.get("s3", {})
        bucket = s3info.get("bucket", {}).get("name", BUCKET)
        key = s3info.get("object", {}).get("key")
        if not key:
            raise ValueError("S3 event missing object key")
        if not key.lower().endswith(".csv"):
            return {"status": "ignored", "reason": "not a .csv", "key": key}

        # Use the bucket from event if present (multi-bucket scenarios)
        global BUCKET
        BUCKET = bucket

        target_key = os.environ.get("TARGET_TEMPLATE_KEY", f"{SOURCE_PREFIX.rstrip('/')}/nasmatch-portfolio.xlsx")
        output_key = os.environ.get("OUTPUT_KEY_TEMPLATE", f"{OUTPUT_PREFIX.rstrip('/')}/nasmatch-portfolio-updated.xlsx")

        # Ensure prefixes
        if not target_key.startswith(SOURCE_PREFIX) and not target_key.startswith(OUTPUT_PREFIX):
            target_key = f"{SOURCE_PREFIX}{target_key}"
        if not output_key.startswith(OUTPUT_PREFIX):
            output_key = f"{OUTPUT_PREFIX}{output_key}"

        csv_bytes = _get_obj_bytes(BUCKET, key)
        rows = _read_positions_csv(csv_bytes)
        wb = _load_workbook_from_s3(target_key)
        ws = _ensure_consolidate_sheet(wb)
        _write_consolidate(ws, rows)

        buf = io.BytesIO(); wb.save(buf); buf.seek(0)
        _put_obj_bytes(
            BUCKET, output_key, buf.read(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        return {"status": "ok", "bucket": BUCKET, "output_key": output_key, "wrote_rows": len(rows), "triggered_by": key}

    # Case 1: direct JSON (manual invoke)
    src_key = event.get("source_key")
    tgt_key = event.get("target_key")
    out_key = event.get("output_key")

    if not src_key or not src_key.lower().endswith(".csv"):
        raise ValueError("source_key is required and must be a .csv")

    if not tgt_key or not tgt_key.lower().endswith(".xlsx"):
        tgt_key = f"{SOURCE_PREFIX.rstrip('/')}/nasmatch-portfolio.xlsx"
    if not out_key:
        out_key = f"{OUTPUT_PREFIX.rstrip('/')}/nasmatch-portfolio-updated.xlsx"

    if not src_key.startswith(SOURCE_PREFIX):
        src_key = f"{SOURCE_PREFIX}{src_key}"
    if not tgt_key.startswith(SOURCE_PREFIX) and not tgt_key.startswith(OUTPUT_PREFIX):
        tgt_key = f"{SOURCE_PREFIX}{tgt_key}"
    if not out_key.startswith(OUTPUT_PREFIX):
        out_key = f"{OUTPUT_PREFIX}{out_key}"

    csv_bytes = _get_obj_bytes(BUCKET, src_key)
    rows = _read_positions_csv(csv_bytes)
    wb = _load_workbook_from_s3(tgt_key)
    ws = _ensure_consolidate_sheet(wb)
    _write_consolidate(ws, rows)

    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    _put_obj_bytes(
        BUCKET, out_key, buf.read(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return {"status": "ok", "bucket": BUCKET, "output_key": out_key, "wrote_rows": len(rows)}
