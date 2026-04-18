# SQL Agent Backend

FastAPI backend for the SQL Agent application.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables:
```bash
cp .env.example .env
# Edit .env and add your OpenAI API key
```

3. Run the server:
```bash
python main.py
# or
uvicorn main:app --reload
```

## API Endpoints

- `POST /api/connect` - Connect to database and extract schema
- `GET /api/schema/{connection_id}` - Get database schema
- `GET /api/schema/{connection_id}/formatted` - Get formatted schema for LLM
- `POST /api/query` - Execute natural language query
- `POST /api/query/execute-sql` - Execute raw SQL query
- `POST /api/download/{connection_id}` - Download query results
- `GET /api/health` - Health check

## Notes

- Make sure you have ODBC Driver 17 for SQL Server installed
- For Windows, download from Microsoft
- For Linux/Mac, install unixODBC and the appropriate driver



