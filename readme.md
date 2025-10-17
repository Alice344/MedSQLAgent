# Medical Database SQL Agent

A natural language to SQL query system powered by Large Language Models (LLMs) for medical databases.

## Features

- 🤖 Convert natural language to SQL queries using LLMs
- 🗄️ Support for MySQL, PostgreSQL, and SQLite databases
- 📊 Interactive web interface with Streamlit
- 📈 Data visualization with Plotly
- 📥 Automatic CSV export
- 🔒 SQL injection protection
- 📝 Query history tracking

## Project Structure

```
SQLAgent/
├── config/
│   ├── __init__.py
│   └── database.py          # Database connection configuration
├── agents/
│   ├── __init__.py
│   └── sql_agent.py         # SQL generation agent
├── utils/
│   ├── __init__.py
│   └── db_connector.py      # Database connector
├── app/
│   ├── __init__.py
│   └── streamlit_app.py     # Frontend interface
├── data/
│   └── exports/             # Exported CSV files
├── .env                     # Environment variables (create this)
├── .env.example            # Environment template
├── requirements.txt
└── README.md
```

## Installation

### 1. Clone or Create the Project

```bash
mkdir SQLAgent
cd SQLAgent
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the root directory:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
# Choose your database type
DB_TYPE=mysql

# Database credentials
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=hospital_db

# LLM API keys
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_key_here
MODEL_NAME=gpt-4
```

### 4. Create Folder Structure

```bash
mkdir -p config agents utils app data/exports
```

### 5. Create __init__.py Files

```bash
touch config/__init__.py agents/__init__.py utils/__init__.py app/__init__.py
```

## Quick Start with SQLite (Testing)

For testing, you can use SQLite without setting up a full database server:

### Create a Sample Database

```python
# create_sample_db.py
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import random

# Create database
conn = sqlite3.connect('./data/hospital.db')
cursor = conn.cursor()

# Create patients table
cursor.execute('''
CREATE TABLE IF NOT EXISTS patients (
    patient_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    age INTEGER,
    gender TEXT,
    admission_date DATE,
    diagnosis TEXT,
    department TEXT
)
''')

# Create doctors table
cursor.execute('''
CREATE TABLE IF NOT EXISTS doctors (
    doctor_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    specialty TEXT,
    department TEXT
)
''')

# Insert sample data
patients_data = []
diagnoses = ['Diabetes', 'Hypertension', 'Pneumonia', 'Fracture', 'Cardiac Arrest']
departments = ['Cardiology', 'Orthopedics', 'Internal Medicine', 'Emergency']
genders = ['Male', 'Female']

for i in range(1, 51):
    patient = (
        i,
        f'Patient_{i}',
        random.randint(20, 80),
        random.choice(genders),
        (datetime.now() - timedelta(days=random.randint(1, 90))).strftime('%Y-%m-%d'),
        random.choice(diagnoses),
        random.choice(departments)
    )
    patients_data.append(patient)

cursor.executemany('''
    INSERT INTO patients VALUES (?, ?, ?, ?, ?, ?, ?)
''', patients_data)

# Insert doctors
doctors_data = [
    (1, 'Dr. Smith', 'Cardiologist', 'Cardiology'),
    (2, 'Dr. Johnson', 'Orthopedic Surgeon', 'Orthopedics'),
    (3, 'Dr. Williams', 'Internal Medicine', 'Internal Medicine'),
    (4, 'Dr. Brown', 'Emergency Physician', 'Emergency')
]

cursor.executemany('''
    INSERT INTO doctors VALUES (?, ?, ?, ?)
''', doctors_data)

conn.commit()
conn.close()

print("✓ Sample database created successfully!")
```

Run this script:

```bash
python create_sample_db.py
```

Update your `.env` file:

```env
DB_TYPE=sqlite
SQLITE_PATH=./data/hospital.db
```

## Running the Application

### Start the Streamlit App

```bash
streamlit run app/streamlit_app.py
```

The application will open in your browser at `http://localhost:8501`

## Usage Examples

### Natural Language Queries

Try these example queries in the interface:

1. **Basic queries:**
   - "Show all patients"
   - "Find patients in Cardiology department"
   - "