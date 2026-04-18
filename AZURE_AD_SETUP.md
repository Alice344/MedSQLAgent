# Azure AD MFA Connection Setup

## Your Connection Details

Based on your code, here's how to connect:

### Connection Information:
- **Server**: `ddd.net` (or your actual server)
- **Database**: `hmfhrftgh` (or your actual database)
- **Username**: `dgsdgsdg@UHhospitals.org` (your Azure AD email)
- **Authentication**: Azure AD Interactive (MFA)

## Steps to Connect in Demo

1. **Start the backend** (make sure you're using the real backend, not demo mode):
   ```powershell
   cd F:\sqlagent\backend
   python run.py
   ```

2. **Open `demo.html`** in your browser

3. **Fill in the connection form**:
   - **Server**: `ddd.net` (your server name)
   - **Database**: `hmfhrftgh` (your database name)
   - **Username**: `dgsdgsdg@UHhospitals.org` (your Azure AD email)
   - **Password**: Leave empty (not needed for MFA)
   - **Port**: `1433` (default)
   - **✅ Check "Use Azure AD MFA"** checkbox

4. **Click "Connect to Database"**
   - A browser window will open for Azure AD authentication
   - Complete the MFA process
   - The connection will be established

5. **Test with a query**:
   - Try: "Show me all patients from caboodle.patientdim"
   - Or use natural language: "Show me top 100 records from patientdim table"

## Executing SQL Queries Directly

After connecting, you can:

1. **Use Natural Language**: Type questions and let the LLM generate SQL
2. **Execute Generated SQL**: Click "Execute This SQL Directly" button
3. **Edit and Execute**: You can edit the generated SQL in the code block and execute it

## Example Queries to Test

```sql
-- Select top records
SELECT TOP 100 * FROM caboodle.patientdim;

-- Count records
SELECT COUNT(*) AS TotalPatients FROM caboodle.patientdim;

-- Filter data
SELECT * FROM caboodle.patientdim WHERE [some_column] = 'value';
```

## Important Notes

- **MFA Browser Window**: When using Azure AD MFA, a browser window will automatically open for authentication
- **Autocommit**: Azure AD connections use autocommit mode
- **Timeout**: Connection timeout is set to 30 seconds for MFA (longer than regular SQL auth)
- **No Password Needed**: For MFA, leave password field empty

## Troubleshooting

### If connection fails:
1. Make sure ODBC Driver 17 for SQL Server is installed
2. Verify your server name is correct
3. Check that your Azure AD account has access to the database
4. Ensure the MFA checkbox is checked
5. Complete the MFA authentication in the browser window

### If queries fail:
- Check that table names include schema (e.g., `caboodle.patientdim`)
- Verify you have SELECT permissions on the tables
- For INSERT/UPDATE/DELETE, ensure you have write permissions



