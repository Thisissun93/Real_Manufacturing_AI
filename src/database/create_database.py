from pathlib import Path
import sqlite3

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CSV_PATH = (
    PROJECT_ROOT
    / "Data"
    / "process_monitoring_data.csv"
)

DB_PATH = (
    PROJECT_ROOT
    / "database"
    / "manufacturing_ai.db"
)


def main():

    DB_PATH.parent.mkdir(
        exist_ok=True,
        parents=True,
    )

    df = pd.read_csv(CSV_PATH)

    conn = sqlite3.connect(DB_PATH)

    df.to_sql(
        "process_data",
        conn,
        if_exists="replace",
        index=False,
    )

    conn.close()

    print("=" * 60)
    print("Database Created")
    print("=" * 60)
    print(DB_PATH)
    print()
    print(df.head())


if __name__ == "__main__":
    main()