import os
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

from dotenv import load_dotenv

from guardrails import validate_tables

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=False)

try:
    import pyodbc
except Exception:  # pragma: no cover
    pyodbc = None

DB_PATH = Path(__file__).resolve().parent / "railpulse.db"


def is_azure_sql_enabled() -> bool:
    value = os.getenv("SQL_CONNECTION_STRING", "")
    return bool(value.strip())


def connect_db(db_path: str | Path = DB_PATH):
    if is_azure_sql_enabled():
        if pyodbc is None:
            raise RuntimeError("pyodbc is required when SQL_CONNECTION_STRING is configured.")
        try:
            conn = pyodbc.connect(os.getenv("SQL_CONNECTION_STRING"))
            return conn
        except Exception:
            fallback = os.getenv("ALLOW_SQLITE_FALLBACK", "true").strip().lower()
            if fallback in {"0", "false", "no"}:
                raise

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_db_mode() -> str:
    if not is_azure_sql_enabled():
        return "sqlite"

    try:
        conn = connect_db()
        is_azure = hasattr(conn, "cursor") and pyodbc is not None and isinstance(conn, pyodbc.Connection)
        conn.close()
        return "azure_sql" if is_azure else "sqlite"
    except Exception:
        return "sqlite"


def ensure_database(db_path: str | Path = DB_PATH):
    conn = connect_db(db_path)
    is_azure = pyodbc is not None and isinstance(conn, pyodbc.Connection)
    if is_azure:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            return conn
        except Exception:
            conn.close()
            sqlite_conn = sqlite3.connect(str(db_path), check_same_thread=False)
            sqlite_conn.row_factory = sqlite3.Row
            return sqlite_conn

    # Local fallback only for non-Azure demo usage.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stations (
            station_id TEXT PRIMARY KEY,
            station_name TEXT NOT NULL,
            standard_name TEXT,
            longitude REAL,
            latitude REAL,
            link TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            id TEXT PRIMARY KEY,
            short_name TEXT,
            vehicle_type TEXT,
            vehicle_class_code TEXT,
            vehicle_number TEXT,
            link TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS liveboard_records (
            record_id INTEGER PRIMARY KEY AUTOINCREMENT,
            station_id TEXT NOT NULL,
            vehicle_id TEXT NOT NULL,
            destination TEXT,
            scheduled_departure TEXT,
            delay_seconds INTEGER NOT NULL DEFAULT 0,
            platform TEXT,
            canceled INTEGER NOT NULL DEFAULT 0
        )
    """)

    if conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0] == 0:
        now = datetime.utcnow()
        conn.executemany(
            "INSERT INTO stations (station_id, station_name) VALUES (?, ?)",
            [("BXL", "Brussels-Central"), ("GNT", "Ghent-Sint-Pieters")],
        )
        conn.executemany(
            "INSERT INTO vehicles (id, short_name) VALUES (?, ?)",
            [("IC100", "IC 100"), ("IC200", "IC 200"), ("S1", "S1")],
        )
        conn.executemany(
            """
            INSERT INTO liveboard_records
                (station_id, vehicle_id, destination, scheduled_departure, delay_seconds, platform)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("BXL", "IC100", "Oostende", (now - timedelta(hours=2)).isoformat(" "), 780, "5"),
                ("BXL", "IC200", "Antwerpen-Centraal", (now - timedelta(hours=5)).isoformat(" "), 420, "7"),
                ("GNT", "S1", "Brussels-Central", (now - timedelta(hours=3)).isoformat(" "), 180, "2"),
            ],
        )

    conn.commit()
    return conn


def get_latest_data_timestamp(conn) -> str | None:
    """Return the most recent scheduled_departure in the dataset, used as the data's "now".

    The pipeline backfills data one day at a time, so the real wall-clock "now" can be
    ahead of what's actually loaded. All relative-date queries should anchor to this
    value instead of the true current time.
    """
    is_azure = pyodbc is not None and isinstance(conn, pyodbc.Connection)
    table = "dbo.liveboard_records" if is_azure else "liveboard_records"
    query = f"SELECT MAX(scheduled_departure) FROM {table}"
    try:
        if is_azure:
            cursor = conn.cursor()
            cursor.execute(query)
            row = cursor.fetchone()
        else:
            row = conn.execute(query).fetchone()
    except Exception:
        return None

    if not row or row[0] is None:
        return None
    value = row[0]
    return value if isinstance(value, str) else value.isoformat(" ")


def get_schema_summary(conn) -> str:
    tables = [
        ("stations", [
            "station_id NVARCHAR(100)",
            "station_name NVARCHAR(200)",
            "standard_name NVARCHAR(200)",
            "longitude DECIMAL(10,6)",
            "latitude DECIMAL(10,6)",
            "link NVARCHAR(255)",
        ]),
        ("vehicles", [
            "id NVARCHAR(100)",
            "short_name NVARCHAR(100)",
            "vehicle_type NVARCHAR(50)",
            "vehicle_class_code NVARCHAR(20)",
            "vehicle_number NVARCHAR(50)",
            "link NVARCHAR(255)",
        ]),
        ("liveboard_records", [
            "record_id INT IDENTITY(1,1)",
            "station_id NVARCHAR(100)",
            "vehicle_id NVARCHAR(100)",
            "destination NVARCHAR(200)",
            "scheduled_departure DATETIME2",
            "delay_seconds INT",
            "platform NVARCHAR(50)",
            "canceled BIT",
        ]),
    ]
    schema_lines = []
    for table_name, cols in tables:
        schema_lines.append(f"Table: {table_name}")
        schema_lines.append("Columns: " + ", ".join(cols))
    return "\n".join(schema_lines)


def normalize_sql_for_backend(sql: str, backend: str | None = None) -> str:
    if backend is None:
        backend = "azure_sql" if is_azure_sql_enabled() else "sqlite"

    if backend == "azure_sql":
        sql = sql.strip().rstrip(";")
        sql = re.sub(r"datetime\('now',\s*'(-?\d+)\s+hours'\)", lambda m: f"DATEADD(hour, {m.group(1)}, GETDATE())", sql, flags=re.IGNORECASE)
        sql = re.sub(r"datetime\('now',\s*'(-?\d+)\s+days'\)", lambda m: f"DATEADD(day, {m.group(1)}, GETDATE())", sql, flags=re.IGNORECASE)
        sql = re.sub(r"datetime\('now',\s*'(-?\d+)\s+minutes'\)", lambda m: f"DATEADD(minute, {m.group(1)}, GETDATE())", sql, flags=re.IGNORECASE)
        sql = re.sub(r"AVG\(delay_seconds\)\s*/\s*60\.0", "AVG(CAST(delay_seconds AS FLOAT)) / 60.0", sql, flags=re.IGNORECASE)
        sql = re.sub(r"AVG\(delay_seconds\)", "AVG(CAST(delay_seconds AS FLOAT))", sql, flags=re.IGNORECASE)
        sql = sql.replace("datetime('now', '-12 hours')", "DATEADD(hour, -12, GETDATE())")
        sql = sql.replace("datetime('now', '-7 days')", "DATEADD(day, -7, GETDATE())")
        sql = sql.replace("datetime('now', '-1 day')", "DATEADD(day, -1, GETDATE())")
        sql = sql.replace("event_time >=", "CAST(event_time AS DATETIME) >=")
        sql = sql.replace("AS avg_delay_seconds", "AS avg_delay_seconds")
    else:
        sql = re.sub(r"\bdbo\.(stations|vehicles|liveboard_records)\b", r"\1", sql, flags=re.IGNORECASE)
        sql = re.sub(
            r"DATEADD\(hour,\s*(-?\d+),\s*GETDATE\(\)\)",
            lambda m: f"datetime('now', '{m.group(1)} hours')",
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(
            r"DATEADD\(day,\s*(-?\d+),\s*GETDATE\(\)\)",
            lambda m: f"datetime('now', '{m.group(1)} days')",
            sql,
            flags=re.IGNORECASE,
        )
        sql = re.sub(r"CAST\(GETDATE\(\) AS date\)", "date('now')", sql, flags=re.IGNORECASE)
        top_match = re.search(r"\bTOP\s+(\d+)\b", sql, flags=re.IGNORECASE)
        if top_match:
            sql = re.sub(r"\s+TOP\s+\d+\s+", " ", sql, count=1, flags=re.IGNORECASE)
            sql = f"{sql.rstrip(';')} LIMIT {top_match.group(1)}"
    return sql


def validate_sql(sql: str) -> str:
    forbidden = [
        "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "ATTACH", "DETACH",
        "CREATE", "TRUNCATE", "EXEC", "PRAGMA", "GRANT", "REVOKE"
    ]
    upper = sql.upper()
    for token in forbidden:
        if token in upper:
            raise ValueError(f"Blocked SQL keyword: {token}")
    if not upper.strip().startswith("SELECT"):
        raise ValueError("Only SELECT statements are allowed.")

    allowed, reason = validate_tables(sql)
    if not allowed:
        raise ValueError(reason)

    return normalize_sql_for_backend(sql)


def apply_data_anchor(sql: str, anchor: str | None, backend: str) -> str:
    """Replace "now" references in generated SQL with the latest data timestamp."""
    if not anchor:
        return sql
    if backend == "azure_sql":
        return re.sub(r"GETDATE\(\)", f"CAST('{anchor}' AS DATETIME2)", sql, flags=re.IGNORECASE)
    return sql.replace("'now'", f"'{anchor}'")


def execute_select(conn, sql: str, data_anchor: str | None = None) -> List[Dict[str, Any]]:
    safe_sql = validate_sql(sql)
    is_azure = pyodbc is not None and isinstance(conn, pyodbc.Connection)
    backend = "azure_sql" if is_azure else "sqlite"
    safe_sql = normalize_sql_for_backend(safe_sql, backend)
    if data_anchor is None:
        data_anchor = get_latest_data_timestamp(conn)
    safe_sql = apply_data_anchor(safe_sql, data_anchor, backend)
    if is_azure:
        cursor = conn.cursor()
        cursor.execute(safe_sql)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    rows = conn.execute(safe_sql).fetchall()
    return [dict(row) for row in rows]


def summarize_rows(rows: List[Dict[str, Any]], question: str) -> str:
    if not rows:
        return "No matching records were found for this request."

    first = rows[0]
    label = next(iter(first.keys()))
    value = first[label]
    if isinstance(value, (int, float)):
        return f"The strongest result is {value}, based on the current data for: {question}."
    return f"The most relevant observation was: {value}."
