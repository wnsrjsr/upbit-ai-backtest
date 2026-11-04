import sqlite3
import pandas as pd

db = sqlite3.connect("paper_trading.db")
try:
    df = pd.read_sql_query("SELECT * FROM trades ORDER BY id", db)
    df.to_csv("trades.csv", index=False, encoding="utf-8-sig")
    print(f"trades.csv 저장 완료: {len(df)}건")
finally:
    db.close()
