"""Data connectors and schema validation for the U.S. Media Ratings app.

CSV and Excel work entirely locally. SQL readers are read-only and fetch a
bounded number of rows from a single named table.
"""
from __future__ import annotations

import csv
from contextlib import closing
from io import BytesIO, StringIO
from pathlib import Path
import re
import sqlite3
import unicodedata

import pandas as pd

MEDIA_ALIASES = {
    "date": ("dates", "air_date", "event_date", "broadcast_date", "report_date", "day", "datetime", "timestamp", "telecast_date"),
    "region": ("market", "dma", "geography", "geo", "area", "territory", "location"),
    "platform": ("medium", "distribution", "service", "device", "channel_type", "source_platform", "data_stream"),
    "network": ("broadcaster", "station", "channel", "publisher", "media_network", "viewing_source"),
    "program": ("show", "title", "program_name", "show_name", "content", "event", "campaign"),
    "genre": ("category", "content_type", "program_type", "segment", "daypart"),
    "viewers": ("audience", "audience_size", "total_viewers", "viewer_count", "viewership", "unique_viewers", "reach"),
    "impressions": ("total_impressions", "impression_count", "ad_impressions", "views", "view_count", "imp", "imp_000", "impressions_000", "impressions_thousands", "total_imp"),
    "rating_pct": ("rating", "rating_percent", "rating_percentage", "audience_rating", "tv_rating", "rtg", "rtg_pct", "rtg_x_x"),
    "ad_spend_usd": ("ad_spend", "spend", "media_spend", "cost", "advertising_spend", "budget"),
    "watch_minutes": ("minutes_watched", "watch_time", "viewing_minutes", "total_minutes", "duration_minutes"),
}
CANONICAL_NUMERICS = ("viewers", "impressions", "rating_pct", "shr", "share", "share_pct", "ad_spend_usd", "watch_minutes")
SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SourceDataError(ValueError):
    """Raised for inputs that cannot power the dashboard."""


def normalize_column_name(value: object) -> str:
    """Turn human column labels into stable snake_case identifiers."""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text).lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "unnamed_column"


def _alias_columns(columns: list[str]) -> tuple[dict[str, str], list[str]]:
    aliases = {alias: canonical for canonical, values in MEDIA_ALIASES.items() for alias in (canonical, *values)}
    occupied = set(columns)
    renames: dict[str, str] = {}
    notes: list[str] = []
    for column in columns:
        canonical = aliases.get(column)
        if canonical and column != canonical and canonical not in occupied and canonical not in renames.values():
            renames[column] = canonical
            occupied.add(canonical)
            notes.append(f"{column} -> {canonical}")
    return renames, notes


def _parse_date_series(series: pd.Series) -> tuple[pd.Series, float, str]:
    """Parse ISO, U.S./international text, Excel serial, and Unix dates."""
    non_null = int(series.notna().sum())
    if non_null == 0:
        return pd.to_datetime(series, errors="coerce"), 0.0, "empty"
    if pd.api.types.is_datetime64_any_dtype(series):
        parsed = pd.to_datetime(series, errors="coerce")
        return parsed, float(parsed.notna().sum() / non_null), "datetime"
    numeric = pd.to_numeric(series, errors="coerce")
    numeric_ratio = float(numeric.notna().sum() / non_null)
    if numeric_ratio >= 0.9:
        median = float(numeric.dropna().median())
        if 20_000 <= median <= 100_000:
            parsed = pd.to_datetime(numeric, unit="D", origin="1899-12-30", errors="coerce")
            return parsed, float(parsed.notna().sum() / non_null), "Excel serial"
        if 1_000_000_000 <= median < 10_000_000_000:
            parsed = pd.to_datetime(numeric, unit="s", errors="coerce")
            return parsed, float(parsed.notna().sum() / non_null), "Unix seconds"
        if 1_000_000_000_000 <= median < 10_000_000_000_000:
            parsed = pd.to_datetime(numeric, unit="ms", errors="coerce")
            return parsed, float(parsed.notna().sum() / non_null), "Unix milliseconds"
    text = series.astype("string").str.strip()
    us = pd.to_datetime(text, errors="coerce", format="mixed", dayfirst=False)
    international = pd.to_datetime(text, errors="coerce", format="mixed", dayfirst=True)
    parsed, style = (international, "mixed/day-first") if international.notna().sum() > us.notna().sum() else (us, "mixed/month-first")
    return parsed, float(parsed.notna().sum() / non_null), style


def _parse_numeric_series(series: pd.Series) -> tuple[pd.Series, float]:
    """Parse common numeric text, including currency, percent, commas, and K/M/B suffixes."""
    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        parsed = pd.to_numeric(series, errors="coerce")
        return parsed, 1.0
    non_null = int(series.notna().sum())
    if non_null == 0:
        return pd.to_numeric(series, errors="coerce"), 0.0
    text = series.astype("string").str.strip()
    negative = text.str.match(r"^\(.*\)$", na=False)
    suffix = text.str.extract(r"(?i)([kmb])\s*%?\s*$", expand=False).str.lower()
    multipliers = suffix.map({"k": 1_000.0, "m": 1_000_000.0, "b": 1_000_000_000.0}).fillna(1.0)
    cleaned = text.str.replace(r"^\((.*)\)$", r"\1", regex=True)
    cleaned = cleaned.str.replace(r"(?i)[kmb]\s*%?\s*$", "", regex=True)
    cleaned = cleaned.str.replace(r"[^0-9eE+\-.]", "", regex=True)
    parsed = pd.to_numeric(cleaned, errors="coerce") * multipliers
    parsed = parsed.where(~negative, -parsed)
    return parsed, float(parsed.notna().sum() / non_null)


def classify_columns(df: pd.DataFrame) -> dict[str, list[str]]:
    """Return columns that can be used as dates, numeric metrics, or dimensions."""
    dates = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
    numerics = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]
    ignored = set(dates + numerics + ["data_source"])
    dimensions = [c for c in df.columns if c not in ignored and df[c].notna().any()]
    return {"dates": dates, "numerics": numerics, "dimensions": dimensions}


def prepare_data(df: pd.DataFrame, source_label: str) -> pd.DataFrame:
    """Normalize names and infer useful types while preserving unfamiliar columns."""
    if df.empty:
        raise SourceDataError("This source contains no rows.")
    df = df.copy()
    original_columns = [str(col) for col in df.columns]
    normalized = [normalize_column_name(col) for col in original_columns]
    if len(normalized) != len(set(normalized)):
        raise SourceDataError("Duplicate column names after normalization. Rename the repeated columns.")
    df.columns = normalized
    renames, alias_notes = _alias_columns(list(df.columns))
    df = df.rename(columns=renames)
    date_notes: list[str] = []
    numeric_notes: list[str] = []

    for column in list(df.columns):
        name_suggests_date = bool(re.search(r"(^|_)(date|dates|day|time|timestamp|month)(_|$)", column))
        if column == "date" or name_suggests_date:
            parsed, ratio, style = _parse_date_series(df[column])
            if ratio >= 0.70:
                df[column] = parsed
                date_notes.append(f"{column} ({style}, {ratio:.0%} parsed)")

    for column in list(df.columns):
        if pd.api.types.is_datetime64_any_dtype(df[column]) or pd.api.types.is_bool_dtype(df[column]):
            continue
        looks_like_identifier = bool(re.search(r"(^|_)(id|zip|postal|phone|year)(_|$)", column))
        parsed, ratio = _parse_numeric_series(df[column])
        threshold = 0.70 if column in CANONICAL_NUMERICS else 0.90
        if not looks_like_identifier and ratio >= threshold:
            df[column] = parsed
            if not pd.api.types.is_numeric_dtype(df[column].dtype):
                continue
            numeric_notes.append(f"{column} ({ratio:.0%} parsed)")
        elif pd.api.types.is_object_dtype(df[column]) or pd.api.types.is_string_dtype(df[column]):
            df[column] = df[column].astype("string").str.strip().replace("", pd.NA)

    if "data_source" not in df.columns:
        df["data_source"] = source_label
    schema = classify_columns(df)
    if not schema["numerics"]:
        raise SourceDataError("No numeric metric column could be detected. Check the values or choose a different table/sheet.")
    df.attrs["preparation_report"] = {
        "original_columns": original_columns,
        "renamed_aliases": alias_notes,
        "detected_dates": date_notes,
        "detected_numerics": numeric_notes,
        **schema,
    }
    return df


def find_csv_table_bounds(text: str) -> tuple[int, int, str]:
    """Locate the header row index, table end line, and separator for delimited text.
    
    Robustly handles files with leading report title/metadata lines and trailing footers/notes.
    """
    lines = text.splitlines()
    if not lines:
        return 0, 0, ","

    delims = [",", "\t", ";", "|"]
    best_line_idx = -1
    best_delim = ","
    max_cols = 0

    # 1. Search for header candidate within the first 60 lines
    for idx, line in enumerate(lines[:60]):
        stripped = line.strip()
        if not stripped:
            continue
        for d in delims:
            try:
                reader = csv.reader([line], delimiter=d)
                row = next(reader)
                non_empty = [c.strip() for c in row if c.strip()]
                if len(non_empty) >= 2 and len(non_empty) > max_cols:
                    # Check if at least one subsequent non-empty row has a comparable column count
                    next_has_match = False
                    for next_idx in range(idx + 1, min(idx + 6, len(lines))):
                        next_line = lines[next_idx].strip()
                        if not next_line:
                            continue
                        next_row = next(csv.reader([next_line], delimiter=d))
                        if len(next_row) >= len(non_empty) - 1:
                            next_has_match = True
                            break
                    if next_has_match or len(non_empty) >= 3 or len(lines) <= 2:
                        max_cols = len(non_empty)
                        best_line_idx = idx
                        best_delim = d
            except Exception:
                continue

    if best_line_idx == -1:
        best_line_idx = 0
        best_delim = ","
        for l in lines:
            if l.strip():
                counts = {d: l.count(d) for d in delims}
                best_delim = max(counts, key=counts.get) if max(counts.values()) > 0 else ","
                break

    end_line_idx = len(lines)
    header_col_count = max_cols
    consecutive_empty = 0

    footer_markers = (
        "copyright", "all rights reserved", "sheet reference",
        "report name:", "report type:", "report id:", "submitted by:",
        "selections", "data availability", "general notes:"
    )

    for idx in range(best_line_idx + 1, len(lines)):
        line = lines[idx].strip()
        if not line:
            consecutive_empty += 1
            if consecutive_empty >= 2:
                end_line_idx = idx - consecutive_empty + 1
                break
            continue
        consecutive_empty = 0

        lower = line.lower()
        if any(marker in lower for marker in footer_markers):
            end_line_idx = idx
            break

        try:
            row = next(csv.reader([line], delimiter=best_delim))
            non_empty = [c.strip() for c in row if c.strip()]
            if header_col_count >= 4 and len(non_empty) <= 1:
                end_line_idx = idx
                break
        except Exception:
            end_line_idx = idx
            break

    return best_line_idx, end_line_idx, best_delim


def read_csv_data(payload: bytes) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            text = payload.decode(encoding)
            start, end, delim = find_csv_table_bounds(text)
            lines = text.splitlines()[start:end]
            if not lines:
                continue
            cleaned_text = "\n".join(lines)
            return pd.read_csv(StringIO(cleaned_text), delimiter=delim)
        except Exception as exc:
            last_error = exc
            try:
                return pd.read_csv(BytesIO(payload), sep=None, engine="python", encoding=encoding)
            except Exception:
                pass
    raise SourceDataError(f"Could not read the CSV file: {last_error}")


def list_excel_sheets(payload: bytes) -> list[str]:
    with pd.ExcelFile(BytesIO(payload), engine="openpyxl") as workbook:
        return workbook.sheet_names


def read_excel_data(payload: bytes, sheet: str) -> pd.DataFrame:
    df_all = pd.read_excel(BytesIO(payload), sheet_name=sheet, header=None, engine="openpyxl")
    if df_all.empty:
        raise SourceDataError("This worksheet is empty.")

    # Find the header row in the first 40 rows
    best_row = 0
    max_non_empty = 0
    for r_idx in range(min(40, len(df_all))):
        row_vals = [
            str(v).strip()
            for v in df_all.iloc[r_idx]
            if pd.notna(v) and str(v).strip() and str(v).strip().lower() != "nan"
        ]
        if len(row_vals) > max_non_empty and len(row_vals) >= 2:
            max_non_empty = len(row_vals)
            best_row = r_idx

    header_cols = [
        str(v).strip() if pd.notna(v) else f"unnamed_{i}"
        for i, v in enumerate(df_all.iloc[best_row])
    ]
    df_table = df_all.iloc[best_row + 1:].copy()
    df_table.columns = header_cols

    footer_markers = (
        "copyright", "all rights reserved", "sheet reference",
        "report name:", "report type:", "report id:", "submitted by:",
        "selections", "data availability", "general notes:"
    )

    end_row = len(df_table)
    consecutive_empty = 0
    for idx in range(len(df_table)):
        row = df_table.iloc[idx]
        first_cell = str(row.iloc[0]).lower().strip() if pd.notna(row.iloc[0]) else ""
        if any(marker in first_cell for marker in footer_markers):
            end_row = idx
            break
        non_na = [
            v for v in row
            if pd.notna(v) and str(v).strip() and str(v).strip().lower() != "nan"
        ]
        if len(non_na) == 0:
            consecutive_empty += 1
            if consecutive_empty >= 2:
                end_row = idx - consecutive_empty + 1
                break
        else:
            consecutive_empty = 0

    clean_df = df_table.iloc[:end_row].dropna(how="all").copy()
    if clean_df.empty:
        raise SourceDataError("No data rows found in worksheet.")
    return clean_df


def _safe_identifier(value: str, kind: str) -> str:
    value = value.strip()
    if not SQL_IDENTIFIER.fullmatch(value):
        raise SourceDataError(f"Invalid {kind}: use letters, digits and underscores, starting with a letter or underscore.")
    return value


def read_sqlite_data(db_path: str, table: str, limit: int) -> pd.DataFrame:
    table = _safe_identifier(table, "table name")
    path = Path(db_path).expanduser().resolve()
    if not path.is_file():
        raise SourceDataError(f"SQLite database does not exist: {path}")
    # URI read-only mode prevents accidentally creating or changing the database.
    uri = path.as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=10)) as conn:
        return pd.read_sql_query(f'SELECT * FROM "{table}" LIMIT ?', conn, params=(int(limit),))


def read_server_data(
    db_kind: str, host: str, port: int, database: str, username: str,
    password: str, schema: str, table: str, limit: int,
) -> pd.DataFrame:
    """Use SQLAlchemy reflection to quote table/schema identifiers safely."""
    from sqlalchemy import MetaData, Table, create_engine, select
    from sqlalchemy.engine import URL

    drivers = {
        "PostgreSQL": "postgresql+psycopg",
        "MySQL": "mysql+pymysql",
        "SQL Server": "mssql+pyodbc",
    }
    if db_kind not in drivers:
        raise SourceDataError("Unsupported SQL database type.")
    table = _safe_identifier(table, "table name")
    schema = _safe_identifier(schema, "schema") if schema.strip() else None
    if not all([host.strip(), database.strip(), username.strip()]):
        raise SourceDataError("Host, database and username must be filled in.")
    if db_kind == "SQL Server":
        url = URL.create(
            drivers[db_kind], username=username, password=password,
            host=host, port=int(port), database=database,
            query={"driver": "ODBC Driver 18 for SQL Server"},
        )
    else:
        url = URL.create(
            drivers[db_kind], username=username, password=password,
            host=host, port=int(port), database=database,
        )
    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 10} if db_kind == "PostgreSQL" else {})
    try:
        metadata = MetaData()
        table_obj = Table(table, metadata, schema=schema, autoload_with=engine)
        statement = select(table_obj).limit(int(limit))
        with engine.connect() as connection:
            return pd.read_sql_query(statement, connection)
    finally:
        engine.dispose()
