"""Adaptive multi-source media intelligence dashboard."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from data_sources import (
    classify_columns,
    list_excel_sheets,
    prepare_data,
    read_csv_data,
    read_excel_data,
    read_server_data,
    read_sqlite_data,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
SAMPLE_CSV = DATA_DIR / "media_ratings_synthetic.csv"
SAMPLE_DB = DATA_DIR / "media_ratings_demo.db"

st.set_page_config(page_title="Media Ratings Intelligence", page_icon="📊", layout="wide")
st.title("📊 U.S. Media Ratings Intelligence")


@st.cache_data(show_spinner=False)
def load_sample_csv() -> pd.DataFrame:
    return prepare_data(pd.read_csv(SAMPLE_CSV), "Synthetic demo data")


def display_name(column: str) -> str:
    return column.replace("_", " ").title()


def compact_number(value: float) -> str:
    if pd.isna(value):
        return "N/A"
    absolute = abs(float(value))
    for threshold, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if absolute >= threshold:
            return f"{value / threshold:,.2f}{suffix}"
    return f"{value:,.2f}"


def preferred(items: list[str], choices: tuple[str, ...], fallback: int = 0) -> int:
    for choice in choices:
        if choice in items:
            return items.index(choice)
    return fallback


with st.sidebar:
    st.header("Data source")
    source = st.selectbox(
        "Choose your data source",
        ["Built-in sample CSV", "Upload CSV", "Upload Excel", "SQL database"],
    )
    max_rows = 25_000
    try:
        if source == "Built-in sample CSV":
            if not SAMPLE_CSV.is_file():
                st.error("Demo CSV not found. Run python generate_data.py first.")
                st.stop()
            all_df = load_sample_csv()
            source_label = "Synthetic demo CSV"
        elif source == "Upload CSV":
            file = st.file_uploader("Upload your CSV file", type=["csv"], key="csv_source")
            if file is None:
                st.info("Select a CSV file to load your dashboard.")
                st.stop()
            all_df = prepare_data(read_csv_data(file.getvalue()), "Uploaded CSV")
            source_label = file.name
        elif source == "Upload Excel":
            file = st.file_uploader("Upload your Excel workbook", type=["xlsx"], key="excel_source")
            if file is None:
                st.info("Select an .xlsx workbook to load your dashboard.")
                st.stop()
            sheet_names = list_excel_sheets(file.getvalue())
            sheet = st.selectbox("Worksheet", sheet_names)
            all_df = prepare_data(read_excel_data(file.getvalue(), sheet), "Uploaded Excel")
            source_label = f"{file.name} / {sheet}"
        else:
            sql_type = st.selectbox("SQL database type", ["SQLite", "PostgreSQL", "MySQL", "SQL Server"])
            table_name = st.text_input("Table name", "ratings")
            max_rows = st.number_input(
                "Maximum rows to fetch", min_value=100, max_value=100_000, value=25_000, step=1_000
            )
            if sql_type == "SQLite":
                sqlite_path = st.text_input("SQLite file path", value=str(SAMPLE_DB))
                sql_context = (sql_type, sqlite_path, table_name, int(max_rows))
                st.caption("The project includes a demo SQLite database ready to use.")
            else:
                default_ports = {"PostgreSQL": 5432, "MySQL": 3306, "SQL Server": 1433}
                host = st.text_input("Host", value="localhost")
                port = st.number_input("Port", min_value=1, max_value=65_535, value=default_ports[sql_type])
                database = st.text_input("Database name", value="")
                schema_name = st.text_input("Schema (optional)", "")
                username = st.text_input("Read-only username", value="")
                password = st.text_input("Password", type="password")
                sql_context = (
                    sql_type, host, int(port), database, schema_name, username, table_name, int(max_rows)
                )
            if st.button("Connect / refresh SQL data", width="stretch"):
                try:
                    with st.spinner("Reading source data..."):
                        if sql_type == "SQLite":
                            raw = read_sqlite_data(sqlite_path, table_name, int(max_rows))
                        else:
                            raw = read_server_data(
                                sql_type, host, int(port), database, username,
                                password, schema_name, table_name, int(max_rows),
                            )
                        result = prepare_data(raw, f"SQL: {sql_type}")
                    st.session_state["sql_source_context"] = sql_context
                    st.session_state["sql_source_dataframe"] = result
                except Exception as exc:
                    st.error(f"Could not load SQL data: {exc}")
                    st.stop()
            if st.session_state.get("sql_source_context") != sql_context:
                st.info("Enter SQL connection details and click 'Connect / refresh SQL data'.")
                st.stop()
            all_df = st.session_state["sql_source_dataframe"]
            source_label = f"{sql_type}: {table_name} (up to {int(max_rows):,} rows)"
            if len(all_df) == int(max_rows):
                st.warning("Row limit reached; the dataset may be truncated. Increase the limit if needed.")
    except Exception as exc:
        st.error(f"Data source error: {exc}")
        st.caption("The source needs headers and at least one recognizable numeric metric column.")
        st.stop()
    st.caption(f"Loaded: {len(all_df):,} rows")

is_demo = source == "Built-in sample CSV" or (
    source == "SQL database"
    and sql_type == "SQLite"
    and "media_ratings_demo.db" in sqlite_path
)
if is_demo:
    st.caption("Portfolio demonstration | All audience metrics are synthetic, not measured ratings.")
else:
    st.caption("Using supplied data. Validate licensing, definitions, and quality before making claims.")
st.caption(f"Current source: {source_label}")

schema = classify_columns(all_df)
date_columns = schema["dates"]
numeric_columns = schema["numerics"]
dimension_columns = schema["dimensions"]
report = all_df.attrs.get("preparation_report", {})

with st.sidebar:
    with st.expander("Detected data structure", expanded=False):
        st.write(f"**Date columns:** {', '.join(date_columns) or 'None'}")
        st.write(f"**Numeric metrics:** {', '.join(numeric_columns)}")
        st.write(f"**Dimensions:** {', '.join(dimension_columns) or 'None'}")
        if report.get("renamed_aliases"):
            st.caption("Automatic mappings: " + "; ".join(report["renamed_aliases"]))
        if report.get("detected_dates"):
            st.caption("Date parsing: " + "; ".join(report["detected_dates"]))

    st.header("Analysis setup")
    date_options = ["No date column"] + date_columns
    date_column = st.selectbox("Date column", date_options, index=1 if date_columns else 0)
    primary_metric = st.selectbox(
        "Primary metric",
        numeric_columns,
        index=preferred(numeric_columns, ("viewers", "impressions", "rating_pct", "shr", "share_pct")),
        format_func=display_name,
    )
    group_options = ["All rows"] + dimension_columns
    default_group = preferred(group_options, ("platform", "genre", "network", "program", "demo"), 1 if dimension_columns else 0)
    group_column = st.selectbox(
        "Group charts by", group_options, index=default_group, format_func=display_name
    )
    default_kpis = [primary_metric] + [c for c in numeric_columns if c != primary_metric][:2]
    kpi_metrics = st.multiselect(
        "KPI metrics", numeric_columns, default=default_kpis, format_func=display_name
    )

    st.header("Filters")
    filter_candidates = [c for c in dimension_columns if all_df[c].nunique(dropna=True) <= 200]
    preferred_filters = [c for c in ("platform", "region", "genre", "network", "program", "demo") if c in filter_candidates]
    filter_columns = st.multiselect(
        "Filter columns",
        filter_candidates,
        default=preferred_filters or filter_candidates[:2],
        format_func=display_name,
    )

filtered = all_df.copy()
with st.sidebar:
    for column in filter_columns:
        values = sorted(filtered[column].dropna().astype(str).unique().tolist())
        selected = st.multiselect(display_name(column), values, default=values, key=f"filter_{column}")
        filtered = filtered[filtered[column].astype("string").isin(selected)]

    start = end = None
    if date_column != "No date column":
        valid_dates = all_df[date_column].dropna()
        if not valid_dates.empty:
            min_date = valid_dates.min().date()
            max_date = valid_dates.max().date()
            period = st.date_input(
                "Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date
            )
            if isinstance(period, (tuple, list)) and len(period) == 2:
                start, end = period
                filtered = filtered[
                    filtered[date_column].between(pd.Timestamp(start), pd.Timestamp(end))
                ]
            else:
                st.info("Select both a start and end date.")
                st.stop()
    st.caption("Source is synthetic demo data." if is_demo else "Use only data you are authorized to analyze.")

if filtered.empty:
    st.warning("No rows match the selected filters.")
    st.stop()

dashboard_tab, sql_tab, ai_tab, qa_tab = st.tabs(
    ["Adaptive Dashboard", "SQL Practice", "Local AI Insights", "Data Quality"]
)

with dashboard_tab:
    st.subheader("Automatically detected metrics")
    visible_kpis = kpi_metrics[:3]
    cards = st.columns(len(visible_kpis) + 1)
    for card, metric in zip(cards, visible_kpis):
        use_mean = any(token in metric for token in ("pct", "percent", "rate", "average", "avg", "shr", "share"))
        value = filtered[metric].mean() if use_mean else filtered[metric].sum(min_count=1)
        card.metric(("Average " if use_mean else "Total ") + display_name(metric), compact_number(value))
    cards[-1].metric("Rows", f"{len(filtered):,}")
    if len(kpi_metrics) > 3:
        st.caption("The first three selected KPI metrics are shown as cards; all remain available below.")

    if date_column != "No date column":
        st.subheader(f"Monthly {display_name(primary_metric)} trend")
        trend_source = filtered.dropna(subset=[date_column]).copy()
        trend_source["period"] = trend_source[date_column].dt.to_period("M").astype(str)
        if group_column == "All rows":
            trend = trend_source.groupby("period")[primary_metric].sum(min_count=1)
        else:
            trend = trend_source.groupby(["period", group_column], as_index=False)[primary_metric].sum()
            trend = trend.pivot(index="period", columns=group_column, values=primary_metric).fillna(0)
        st.line_chart(trend, y_label=display_name(primary_metric))

    left, right = st.columns(2)
    with left:
        if group_column == "All rows":
            st.subheader("Metric distribution")
            bucket_count = min(20, max(5, len(filtered) // 10))
            distribution = filtered[primary_metric].dropna().value_counts(bins=bucket_count).sort_index()
            distribution.index = distribution.index.astype(str)
            st.bar_chart(distribution)
        else:
            st.subheader(f"{display_name(primary_metric)} by {display_name(group_column)}")
            breakdown = filtered.groupby(group_column)[primary_metric].sum(min_count=1).nlargest(20)
            st.bar_chart(breakdown, y_label=display_name(primary_metric))
    with right:
        st.subheader("Top records")
        show_columns = (
            ([date_column] if date_column != "No date column" else [])
            + ([group_column] if group_column != "All rows" else [])
            + kpi_metrics
        )
        show_columns = list(dict.fromkeys(show_columns))
        st.dataframe(
            filtered.nlargest(10, primary_metric)[show_columns], hide_index=True, width="stretch"
        )

    st.subheader("Explore any detected metric")
    explore_metric = st.selectbox(
        "Metric to explore",
        numeric_columns,
        index=numeric_columns.index(primary_metric),
        format_func=display_name,
    )
    st.dataframe(filtered[explore_metric].describe().rename("Value").to_frame(), width="stretch")

with sql_tab:
    st.subheader("Write SQL against the filtered data")
    st.caption(
        "Only one SELECT query is accepted. The filtered source is copied into a temporary "
        "in-memory SQLite table named `ratings`."
    )
    if group_column != "All rows":
        example = (
            f'SELECT "{group_column}", ROUND(SUM("{primary_metric}"), 2) AS total\n'
            f'FROM ratings\nGROUP BY "{group_column}"\nORDER BY total DESC;'
        )
    else:
        example = (
            f'SELECT COUNT(*) AS rows, ROUND(SUM("{primary_metric}"), 2) AS total\nFROM ratings;'
        )
    query = st.text_area("SQL query", value=example, height=145)
    if st.button("Run SQL query"):
        clean = query.strip()
        forbidden = r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|PRAGMA|REPLACE|VACUUM)\b"
        if (
            not clean.upper().startswith("SELECT ")
            or re.search(forbidden, clean, re.IGNORECASE)
            or clean.rstrip(";").find(";") != -1
        ):
            st.error("Use one read-only SELECT query without additional statements.")
        else:
            try:
                with sqlite3.connect(":memory:") as con:
                    filtered.to_sql("ratings", con, index=False)
                    result = pd.read_sql_query(clean, con)
                st.dataframe(result, hide_index=True, width="stretch")
            except Exception as exc:
                st.error(f"SQL error: {exc}")
    st.caption("Available columns: " + ", ".join(filtered.columns))

with ai_tab:
    st.subheader("Ask your locally running Ollama model for an executive summary")
    st.caption("Only the displayed aggregate summary is sent to your local Ollama service.")
    model_name = st.text_input("Ollama model name", value="llama3.2:latest")
    ai_question = st.text_input(
        "Your question", value="Summarize the major patterns and suggest useful follow-up questions."
    )
    if st.button("Generate local AI insights"):
        if group_column == "All rows":
            group_summary = {"all_rows": round(float(filtered[primary_metric].sum()), 2)}
        else:
            group_summary = (
                filtered.groupby(group_column)[primary_metric].sum().nlargest(10).round(2).to_dict()
            )
        date_context = f" Date range: {start} to {end}." if start and end else ""
        context = (
            f"Source: {source_label}. Rows: {len(filtered)}.{date_context} "
            f"Primary metric: {primary_metric}. Top grouped totals: {group_summary}."
        )
        prompt = (
            "You are an analyst. Use only the supplied aggregate summary. Do not invent causes or "
            "unsupported facts. Distinguish observations from hypotheses. Give 3 concise insights "
            "and 2 follow-up questions.\n"
            f"Data: {context}\nQuestion: {ai_question}"
        )
        try:
            response = requests.post(
                "http://localhost:11434/api/chat",
                json={"model": model_name, "messages": [{"role": "user", "content": prompt}], "stream": False},
                timeout=120,
            )
            response.raise_for_status()
            st.write(response.json().get("message", {}).get("content", "No response returned."))
        except Exception as exc:
            st.error(f"Could not use local Ollama: {exc}. Check that Ollama is running and the model is installed.")

with qa_tab:
    st.subheader("Data quality checks")
    results = {
        "Missing cells": int(all_df.isna().sum().sum()),
        "Fully duplicated rows": int(all_df.duplicated().sum()),
        "Columns containing only missing values": int(all_df.isna().all().sum()),
    }
    if "viewers" in all_df:
        results["Nonpositive viewers"] = int((all_df["viewers"] <= 0).sum())
    if {"viewers", "impressions"}.issubset(all_df.columns):
        results["Viewers above impressions"] = int((all_df["viewers"] > all_df["impressions"]).sum())
    if "rating_pct" in all_df:
        results["Ratings outside 0-100%"] = int(
            ((all_df["rating_pct"] < 0) | (all_df["rating_pct"] > 100)).sum()
        )
    qa_frame = pd.DataFrame(
        [
            {
                "Check": key,
                "Issues found": value,
                "Status": "PASS" if value == 0 else "INVESTIGATE",
            }
            for key, value in results.items()
        ]
    )
    st.dataframe(qa_frame, hide_index=True, width="stretch")

    st.subheader("Column profile")
    profile_rows = []
    for column in all_df.columns:
        samples = all_df[column].dropna().astype(str).head(3).tolist()
        profile_rows.append(
            {
                "Column": column,
                "Detected type": str(all_df[column].dtype),
                "Filled rows": int(all_df[column].notna().sum()),
                "Unique values": int(all_df[column].nunique(dropna=True)),
                "Examples": ", ".join(samples),
            }
        )
    st.dataframe(pd.DataFrame(profile_rows), hide_index=True, width="stretch")
    st.caption(
        "Automatic detection is best-effort. Use the Analysis setup selectors to correct an "
        "ambiguous date, metric, or grouping choice."
    )
