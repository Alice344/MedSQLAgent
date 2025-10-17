import os
import sqlite3
from pathlib import Path
from dotenv import set_key, load_dotenv

# --------------------------
# Step 1: Create directories
# --------------------------
data_dir = Path("./data")
data_dir.mkdir(exist_ok=True)
db_path = data_dir / "hospital.db"

# --------------------------
# Step 2: Create SQLite database and table
# --------------------------
print(f"🧱 Creating SQLite database at: {db_path}")
conn = sqlite3.connect(db_path)

conn.execute("""
CREATE TABLE IF NOT EXISTS visits_summary (
    visit_date TEXT,
    department TEXT,
    diagnosis_group TEXT,
    patient_count INTEGER
)
""")

# Insert sample data
sample_data = [
    ("2024-01-10", "Cardiology", "Heart Failure", 23),
    ("2024-01-10", "Oncology", "Cancer", 12),
    ("2024-02-01", "Cardiology", "Heart Attack", 30),
    ("2024-02-05", "Neurology", "Stroke", 18),
    ("2024-03-12", "Orthopedics", "Fracture", 22),
    ("2024-03-15", "Pediatrics", "Flu", 28),
]
conn.executemany("INSERT INTO visits_summary VALUES (?, ?, ?, ?)", sample_data)
conn.commit()
conn.close()

print("✅ Database created and sample data inserted.")

# --------------------------
# Step 3: Create .env file
# --------------------------
env_path = Path(".env")
if not env_path.exists():
    print("📝 Creating .env configuration file...")
    env_path.write_text("")  # create empty file

load_dotenv(dotenv_path=env_path)  # load existing env (if any)

# set environment variables
set_key(env_path, "DB_TYPE", "sqlite")
set_key(env_path, "SQLITE_PATH", str(db_path))
set_key(env_path, "EXPORT_DIR", "./data/exports/")
set_key(env_path, "LLM_PROVIDER", "openai")
set_key(env_path, "MODEL_NAME", "gpt-4o-mini")

print("✅ .env file configured for SQLite database.")

# --------------------------
# Step 4: Verify connection
# --------------------------
print("🔍 Testing database connection...")
import pandas as pd
from sqlalchemy import create_engine

engine = create_engine(f"sqlite:///{db_path}")
df = pd.read_sql_query("SELECT * FROM visits_summary", engine)
print("✅ Connection successful! Sample query result:")
print(df.head())

print("\n🎉 Setup complete! You can now use DatabaseConfig.get_connection_string() to connect.")