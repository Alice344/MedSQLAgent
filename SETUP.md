# Setup Guide

## Prerequisites

1. **Python 3.8+** - [Download Python](https://www.python.org/downloads/)
2. **Node.js 18+** - [Download Node.js](https://nodejs.org/)
   - **Windows**: Download the LTS version from [nodejs.org](https://nodejs.org/)
   - After installation, restart your terminal/PowerShell
   - Verify installation: `node --version` and `npm --version`
3. **ODBC Driver 17 for SQL Server**:
   - Windows: Download from [Microsoft](https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
   - Linux: Install using package manager
   - Mac: Install via Homebrew
4. **OpenAI API Key** - Get from [OpenAI Platform](https://platform.openai.com/)

## Quick Start

### 1. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment (recommended)
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Note: If you encounter build errors on Windows, make sure you have:
# - Microsoft Visual C++ Build Tools installed (for packages that need compilation)
# - Or use pre-built wheels by upgrading pip: pip install --upgrade pip

# Set up environment variables
# Copy .env.example to .env and edit it
# Add your OPENAI_API_KEY

# Run the server
python run.py
# or
python main.py
```

The backend will be available at `http://localhost:8000`

### 2. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

The frontend will be available at `http://localhost:3000`

## Troubleshooting

### ODBC Driver Issues

If you get connection errors:

1. **Windows**: Make sure you have "ODBC Driver 17 for SQL Server" installed
   - Check in: Control Panel > Administrative Tools > ODBC Data Sources (64-bit) > Drivers tab

2. **Linux**: Install unixODBC and the driver:
   ```bash
   sudo apt-get update
   sudo apt-get install unixodbc unixodbc-dev
   # Then install Microsoft ODBC Driver for SQL Server
   ```

3. **Mac**: Install via Homebrew:
   ```bash
   brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
   brew update
   brew install msodbcsql17
   ```

### Connection String Issues

If you're having trouble connecting to Azure SQL Database:
- Make sure your server allows connections from your IP
- Check firewall settings
- Verify the server name format: `server.database.windows.net`

### OpenAI API Issues

- Make sure your API key is valid
- Check your OpenAI account has credits
- Verify the API key is set in the `.env` file

## Testing the Connection

Once both servers are running:

1. Open `http://localhost:3000` in your browser
2. Enter your database credentials
3. Click "Connect to Database"
4. If successful, you should see the query interface

## Production Deployment

For production:

1. Set `NEXT_PUBLIC_API_URL` to your production backend URL
2. Use environment variables for all secrets
3. Enable HTTPS
4. Consider adding authentication
5. Use a proper database for schema storage (instead of files)
6. Implement connection pooling
7. Add rate limiting

