from pathlib import Path
import sqlite3

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DB_PATH = (
    PROJECT_ROOT
    / "database"
    / "manufacturing_ai.db"
)


def main():

    conn = sqlite3.connect(DB_PATH)

    query = """
    SELECT
        Machine,
        COUNT(*) AS LOT_COUNT,
        AVG(Yield) AS AVG_YIELD
    FROM process_data
    GROUP BY Machine
    ORDER BY AVG_YIELD DESC
    """

    df = pd.read_sql(
        query,
        conn,
    )

    conn.close()

    print(df)


if __name__ == "__main__":
    main()