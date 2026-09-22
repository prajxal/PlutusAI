"""
Data ingestion (Module A).

The browser POSTs the file straight here. There is no presigned-URL round trip
any more, and no 10 MB gateway ceiling to work around -- the two-step dance
existed only to get large files past API Gateway.

Steps: map CSV columns -> internal schema, validate, store, and report rejected
rows instead of failing the whole file. Extra columns are preserved.

Column mapping is heuristic: real CSVs say "Qty Sold" and "Selling Price", not
our field names. A row that cannot be read is reported with a reason and a line
number and the rest of the file still loads -- one bad date should never cost a
business their whole upload.
"""
import csv
import io
import os
import re
import uuid

from shared import config, repository
from shared.errors import ApiError
from shared.log import logger
from shared.models import BusinessRecord, parse_date, parse_number

# Ordered by how specific they are: "unit cost" must win over "unit price"
# before a looser "cost"/"price" match gets a chance.
COLUMN_SYNONYMS = {
    "date": ["date", "orderdate", "saledate", "txndate", "transactiondate", "invoicedate", "day", "billdate"],
    "product": ["product", "productname", "item", "itemname", "sku", "description", "particulars"],
    "units_sold": ["unitssold", "units", "qtysold", "quantitysold", "qty", "quantity", "count", "sold", "nos"],
    "unit_price": ["unitprice", "sellingprice", "saleprice", "priceperunit", "rate", "mrp", "price"],
    "unit_cost": ["unitcost", "costprice", "purchaseprice", "buyingprice", "costperunit", "cogs", "cost"],
}
REQUIRED = ("date", "product", "units_sold", "unit_price", "unit_cost")
MAX_REPORTED_REJECTS = 25


# ------------------------------------------------------------ column mapping --

def normalise(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (header or "").lower())


def map_columns(headers) -> dict:
    """Map this file's headers onto our field names. Returns {field: header}.

    Each header is claimed by at most one field, and the most specific synonym
    wins, so "Cost Price" does not get taken by the price rule.
    """
    normalised = {normalise(h): h for h in headers if h}
    mapping, claimed = {}, set()

    for field, synonyms in COLUMN_SYNONYMS.items():
        for synonym in synonyms:
            for norm, original in normalised.items():
                if original in claimed:
                    continue
                if norm == synonym or (len(synonym) > 4 and synonym in norm):
                    mapping[field] = original
                    claimed.add(original)
                    break
            if field in mapping:
                break

    missing = [f for f in REQUIRED if f not in mapping]
    if missing:
        raise ApiError(
            422,
            "I could not find these columns in your file: "
            + ", ".join(f.replace("_", " ") for f in missing)
            + ". The columns I did find were: "
            + ", ".join(h for h in headers if h),
        )
    return mapping


def parse_rows(reader, mapping):
    """Turn CSV rows into records, collecting the ones that cannot be read.

    Returns (records, rejected). Extra columns the business keeps -- store,
    channel, anything -- are preserved as extras.
    """
    records, rejected = [], []
    extra_headers = [h for h in (reader.fieldnames or []) if h and h not in mapping.values()]

    for line_number, row in enumerate(reader, start=2):  # row 1 is the header
        try:
            units = parse_number(row.get(mapping["units_sold"]), "units sold")
            price = parse_number(row.get(mapping["unit_price"]), "unit price")
            cost = parse_number(row.get(mapping["unit_cost"]), "unit cost")
            product = (row.get(mapping["product"]) or "").strip()
            if not product:
                raise ValueError("missing product name")
            if units < 0 or price < 0 or cost < 0:
                raise ValueError("negative quantity or price")
            record = BusinessRecord(
                date=parse_date(row.get(mapping["date"])),
                product=product,
                units_sold=units,
                unit_price=price,
                unit_cost=cost,
                extras={h: (row.get(h) or "").strip() for h in extra_headers if (row.get(h) or "").strip()},
            )
        except (ValueError, KeyError, TypeError) as exc:
            rejected.append({"line": line_number, "reason": str(exc)})
            continue
        records.append(record)

    return records, rejected


# ------------------------------------------------------------------- ingest --

def ingest_csv_text(business_id: str, filename: str, text: str, replace: bool = True) -> dict:
    """Read a CSV into the business's records."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ApiError(422, "That file has no header row.")

    mapping = map_columns(reader.fieldnames)
    records, rejected = parse_rows(reader, mapping)
    if not records:
        raise ApiError(
            422,
            "I could not read a single row of that file. "
            + (f"The first problem was on line {rejected[0]['line']}: {rejected[0]['reason']}."
               if rejected else ""),
        )

    if replace:
        repository.replace_business_records(business_id, records)
    else:
        repository.put_business_records(business_id, records)

    dates = sorted(r.date for r in records)
    # Merge rather than replace: the business's name is not in the CSV, so a
    # second upload would otherwise wipe it.
    meta = {
        **repository.get_business_meta(business_id),
        "file": filename,
        "rows": len(records),
        "rejected_rows": len(rejected),
        "rejected_detail": rejected[:MAX_REPORTED_REJECTS],
        "from": dates[0],
        "to": dates[-1],
        "products": sorted({r.product for r in records}),
        "column_mapping": mapping,
    }
    repository.put_business_meta(business_id, meta)

    logger.info(
        "Ingested CSV",
        business_id=business_id,
        file=filename,
        accepted=len(records),
        rejected=len(rejected),
    )
    return {"business_id": business_id, "records": len(records), "rejected": rejected, "meta": meta}


# ---------------------------------------------------------------- uploads --

def save_upload(business_id: str, filename: str, data: bytes) -> dict:
    """Keep the raw file, then ingest it.

    The parsed records are the product, but the original is the evidence for
    what the dashboard was built from, so it is kept under a directory owned by
    this business and nobody else.
    """
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise ApiError(413, f"That file is larger than "
                            f"{config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")

    safe = _safe_filename(filename)
    directory = os.path.join(config.UPLOAD_DIR, business_id)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{uuid.uuid4().hex[:8]}-{safe}")
    with open(path, "wb") as fh:
        fh.write(data)

    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ApiError(422, "That file is not text. Export it as CSV and try again.")

    result = ingest_csv_text(business_id, safe, text)
    result["stored_at"] = path
    return result


def _safe_filename(name: str) -> str:
    """Strip anything that could climb out of this business's own directory."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", name.split("/")[-1].split("\\")[-1])
    return cleaned[:80] or "upload.csv"
