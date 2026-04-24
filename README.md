# SQL Agent - Natural Language to SQL

A natural language to SQL agent that connects to SQL Server databases (including Caboodle), extracts schemas, and allows users to query databases using plain English.

## Features

1. **Schema Extraction & Storage**: Automatically extracts and stores table schemas, columns, and foreign key relationships
2. **Azure AD MFA Support**: Secure login with Azure Active Directory Multi-Factor Authentication
3. **Natural Language Queries**: Users can type requests in natural language, and the LLM generates SQL queries
4. **Query Execution**: Executes generated SQL queries on the database
5. **Results Download**: Download query results as CSV or JSON

## Architecture

- **Backend**: FastAPI (Python) - handles database connections, schema extraction, LLM integration, and query execution
- **Frontend Options**:
  - **Streamlit** (Recommended): Modern Python-based web interface
  - **HTML** (No installation): Standalone HTML file that works in any browser

## Quick Start

### 1. Backend Setup

```powershell
cd backend
pip install -r requirements.txt

# Set up environment variables (create .env file)
# Add your OPENAI_API_KEY

# Run the server
python run.py
```

The backend will run on `http://localhost:8000`

### 2. Frontend Setup

#### Option A: Next.js (Recommended)

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000` in your browser.

#### Option B: HTML (No Installation)

Simply open `demo_standalone.html` in your browser - no installation needed!

## Usage

1. **Connect to Database**:
   - Enter your SQL Server credentials
   - For Azure AD MFA: Leave password empty and check "Use Azure AD MFA"
   - Click "Connect" - a browser window will open for Azure AD authentication

2. **Query Database**:
   - **Natural Language**: Type questions like "Show me top 100 records from caboodle.patientdim"
   - **Raw SQL**: Write and execute SQL directly
   - View results in tables
   - Download as CSV or JSON

## Requirements

- Python 3.8+
- ODBC Driver 17 for SQL Server
- OpenAI API key (for LLM functionality)
- Streamlit (for Streamlit frontend, optional)

## Azure AD Connection

The system supports Azure AD authentication with MFA:

```python
# Connection string format
DRIVER={ODBC Driver 17 for SQL Server};
SERVER=your-server.database.windows.net;
DATABASE=your-database;
UID=your-email@domain.com;
Authentication=ActiveDirectoryInteractive;
```

## API Endpoints

- `POST /api/connect` - Connect to database and extract schema
- `GET /api/schema/{connection_id}` - Get database schema
- `POST /api/query` - Execute natural language query
- `POST /api/query/execute-sql/{connection_id}` - Execute raw SQL query
- `POST /api/download/{connection_id}` - Download query results

## License

MIT
