import os, json, logging
from typing import List
import azure.functions as func
import psycopg

EVH_NAME = os.environ["EventHubName"]           # e.g. "app-events"
CRDB_URL = os.environ["CrdbUrl"]                # e.g. postgresql://user:pass@host:26257/defaultdb?sslmode=verify-full&sslrootcert=/tmp/crdb-ca.crt
CRDB_CA_PEM = os.environ.get("CrdbCaPem")       # optional PEM; if set we'll write it to /tmp

# Write CA PEM to disk if provided, and make sure CRDB_URL points to it
if CRDB_CA_PEM:
    ca_path = "/tmp/crdb-ca.crt"
    with open(ca_path, "w") as f:
        f.write(CRDB_CA_PEM)
    if "sslrootcert=" not in CRDB_URL:
        sep = "&" if "?" in CRDB_URL else "?"
        CRDB_URL = f"{CRDB_URL}{sep}sslrootcert={ca_path}"
    if "sslmode=" not in CRDB_URL:
        sep = "&" if "?" in CRDB_URL else "?"
        CRDB_URL = f"{CRDB_URL}{sep}sslmode=verify-full"

def _map_fields(d: dict) -> dict:
    x = dict(d)  # shallow copy
    x["account_id"] = x.pop("accountId", None)
    x["amount_type"] = x.pop("amountType", None)
    x["dispute_id"] = x.pop("disputeId", None)
    x["initial_date"] = x.pop("initialDate", None)
    x["original_amount"] = x.pop("originalAmount", None)
    x["posting_date"] = x.pop("postingDate", None)
    x["reference_key_value"] = x.pop("referenceKeyValue", None)
    x["tran_code"] = x.pop("tranCode", None)
    x["reference_key_type"] = x.pop("referenceKeyType", None)
    x["settlement_date"] = x.pop("settlementDate", None)
    x["transaction_return"] = x.pop("transactionReturn", None)
    return x

def _ensure_table(conn):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS transaction (
      id STRING PRIMARY KEY,
      account_id STRING,
      amount_type STRING,
      dispute_id STRING,
      initial_date TIMESTAMPTZ,
      original_amount DECIMAL,
      posting_date TIMESTAMPTZ,
      reference_key_value STRING,
      tran_code STRING,
      reference_key_type STRING,
      settlement_date TIMESTAMPTZ,
      transaction_return BOOL
    )
    """)
    conn.commit()

def main(events: List[func.EventHubEvent]):
    logging.info("EventHub batch size: %d", len(events))
    with psycopg.connect(CRDB_URL) as conn:
        _ensure_table(conn)
        with conn.cursor() as cur:
            for ev in events:
                try:
                    d = json.loads(ev.get_body().decode("utf-8"))
                    d = _map_fields(d)
                    cols = ",".join(d.keys())
                    vals = [d[k] for k in d.keys()]
                    placeholders = ",".join(["%s"]*len(vals))
                    updates = ",".join([f"{k}=excluded.{k}" for k in d.keys() if k != "id"])
                    sql = f"INSERT INTO transaction ({cols}) VALUES ({placeholders}) ON CONFLICT (id) DO UPDATE SET {updates}"
                    cur.execute(sql, vals)
                except Exception as e:
                    logging.exception("Failed to process event: %s", e)
        conn.commit()
