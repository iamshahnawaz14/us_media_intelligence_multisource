"""Create a demo SQLite database from the bundled synthetic media CSV."""
from pathlib import Path
import sqlite3
import pandas as pd

folder = Path(__file__).resolve().parent / "data"
source = folder / "media_ratings_synthetic.csv"
database = folder / "media_ratings_demo.db"
if not source.is_file():
    raise SystemExit("CSV not found. First run: python generate_data.py")
rows = pd.read_csv(source)
with sqlite3.connect(database) as connection:
    rows.to_sql("ratings", connection, if_exists="replace", index=False)
    connection.execute("CREATE INDEX IF NOT EXISTS ix_ratings_date ON ratings(date)")
print(f"Created {database} with {len(rows):,} synthetic rows in ratings table")
