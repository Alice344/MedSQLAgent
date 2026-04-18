# Quick Start Guide

## Option 1: Install Node.js (Recommended)

To use the full application with the web interface:

1. **Download and Install Node.js**:
   - Go to https://nodejs.org/
   - Download the **LTS (Long Term Support)** version for Windows
   - Run the installer and follow the setup wizard
   - **Important**: Restart your terminal/PowerShell after installation

2. **Verify Installation**:
   ```powershell
   node --version
   npm --version
   ```
   Both commands should show version numbers.

3. **Install Frontend Dependencies**:
   ```powershell
   cd frontend
   npm install
   ```

4. **Run Frontend**:
   ```powershell
   npm run dev
   ```

5. **Open Browser**:
   - Navigate to `http://localhost:3000`

## Option 2: Test Backend API Only (No Frontend Needed)

You can test the backend API directly without installing Node.js:

1. **Backend is already running** on `http://localhost:8000`

2. **Open API Documentation**:
   - Open your browser and go to: `http://localhost:8000/docs`
   - This is an interactive API documentation (Swagger UI)
   - You can test all endpoints directly from here

3. **Test Connection**:
   - Click on `POST /api/connect`
   - Click "Try it out"
   - Enter your database credentials:
     ```json
     {
       "server": "your-server.database.windows.net",
       "database": "Caboodle",
       "username": "your-username",
       "password": "your-password",
       "port": 1433
     }
     ```
   - Click "Execute"
   - Copy the `connection_id` from the response

4. **Test Query**:
   - Click on `POST /api/query`
   - Click "Try it out"
   - Enter:
     ```json
     {
       "natural_language_query": "Show me all tables",
       "connection_id": "your-connection-id-here"
     }
     ```
   - Click "Execute"

## Option 3: Use Postman or Similar Tool

You can use any HTTP client (Postman, Insomnia, curl) to interact with the API:

- Base URL: `http://localhost:8000`
- See `README.md` for all available endpoints

## Troubleshooting

### Node.js Installation Issues

- **After installing Node.js, restart your terminal/PowerShell**
- If `npm` is still not recognized:
  - Check if Node.js is in your PATH: `$env:PATH`
  - Reinstall Node.js and make sure "Add to PATH" is checked
  - Restart your computer if needed

### Backend API Testing

- Make sure backend is running: `http://localhost:8000/api/health` should return `{"status": "healthy"}`
- Check API docs: `http://localhost:8000/docs`


