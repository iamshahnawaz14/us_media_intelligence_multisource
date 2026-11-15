# U.S. Media Ratings Intelligence — Excel / CSV / SQL Edition

This is a replacement version of your existing Streamlit + Ollama project, now with **four data-source choices** in the sidebar:

- Built-in synthetic CSV (works immediately)
- Upload a CSV file from your computer
- Upload an Excel **.xlsx** workbook and select its worksheet
- Connect to a SQL database: **SQLite, PostgreSQL, MySQL or SQL Server**

Your **Audience Dashboard**, **SQL Practice**, **Local AI Insights**, and **Data Quality** tabs all analyze the currently selected data source. When you upload a new file, Streamlit changes the source without editing Python code. SQL sources load when you click **Connect / refresh SQL data**.

## Quick Start & Installation

Anyone can clone and run this project in 3 simple steps:

### 1. Clone the Repository
```bash
git clone https://github.com/iamshahnawaz14/us_media_intelligence_multisource.git
cd us_media_intelligence_multisource
```

### 2. Set Up Virtual Environment & Install Dependencies

**Windows (PowerShell):**
```powershell
py -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\streamlit run app.py
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

### 3. Open in Browser
Open **http://localhost:8501** in your browser. The app starts immediately with the built-in demo dataset!

## Use Excel

Select **Upload Excel**, upload an `.xlsx` file and select the worksheet containing your data. First row should be the column headers. For a quick demo, open `data/media_ratings_synthetic.csv` in Excel and save it as an `.xlsx` workbook, then upload it.

## Use CSV

Select **Upload CSV** and upload your file. For best compatibility, save in UTF-8 CSV format.

## Use SQL

Select **SQL database**.

**SQLite:** Choose SQLite; the default file `data/media_ratings_demo.db` is included. Table name: `ratings`. Click **Connect / refresh SQL data**. For your own `.db` file, enter its local path and a table name.

**PostgreSQL:** Install `psycopg[binary]`, then enter host, port, database, read-only username/password, schema (optional) and table name. Default port 5432.

**MySQL:** Install `pymysql`, then enter host, port, database, read-only username/password and table. Default port 3306.

**SQL Server:** Install `pyodbc` AND Microsoft ODBC Driver 18 for SQL Server, then enter host, port, database, read-only username/password and table. Default port 1433. A correctly configured TLS certificate may be required by ODBC Driver 18.

Optional PowerShell commands:

```powershell
.\.venv\Scripts\python.exe -m pip install "psycopg[binary]>=3.2,<4"  # PostgreSQL
.\.venv\Scripts\python.exe -m pip install "pymysql>=1.1,<2"        # MySQL
.\.venv\Scripts\python.exe -m pip install "pyodbc>=5,<6"          # SQL Server
```

**Security:** Connect only to databases and data you are authorized to access. Use a SELECT-only/read-only DB account. This app retrieves at most the row limit you set, and it does not write changes to source databases. Do not put production credentials into source code or publish private datasets. Your local Ollama assistant sees only the summarized metric context sent to it.

## Automatic schema and format detection

The dashboard no longer requires one fixed set of media columns. A source only needs a header row, at least one data row, and at least one numeric metric. It automatically:

- normalizes headers to `snake_case`
- recognizes common aliases such as `Audience Size` -> `viewers`, `Market` -> `region`, and `Event Date` -> `date`
- parses ISO and mixed text dates, Excel serial dates, and Unix timestamps
- parses commas, currency symbols, percentages, parentheses, and K/M/B numeric suffixes
- retains unfamiliar numeric columns as selectable metrics
- exposes inferred date, primary metric, KPI, grouping, and filter choices in the sidebar so they can be corrected

For example, a file containing `Event Date`, `Campaign Name`, `Audience Size`, and `Revenue USD` can be analyzed without editing Python. The **Detected data structure** panel shows what was inferred. Automatic detection is best-effort: ambiguous dates such as `01/02/2026` may require confirming the interpretation, and identifiers stored as numbers should remain labeled with names such as `customer_id` so they are not treated as metrics.

## Original features retained

- 4 dashboard tabs, including read-only SQL Practice against the selected and filtered data (SQLite in-memory)
- Local Ollama assistant: choose your installed `llama3.2:latest` model
- KPI cards, platform trend charts, program leaderboard, and basic data quality tests
- Default synthetic dataset: never present its numbers as genuine Nielsen or actual sports ratings

## Run tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

This project is intended for local portfolio development. For large databases, a proper data warehouse model and a query-optimized dashboard are a better next step than downloading full raw tables.
