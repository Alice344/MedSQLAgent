# Port 8000 Already in Use - Solutions

## Quick Fix Options

### Option 1: Kill the Process Using Port 8000 (Recommended)

1. **Find the process**:
   ```powershell
   netstat -ano | findstr :8000
   ```
   Note the PID (Process ID) in the last column

2. **Kill the process**:
   ```powershell
   taskkill /PID <PID_NUMBER> /F
   ```
   Replace `<PID_NUMBER>` with the actual PID (e.g., `taskkill /PID 41088 /F`)

3. **Start your backend**:
   ```powershell
   cd F:\sqlagent\backend
   python run.py
   ```

### Option 2: Use a Different Port

1. **Start backend on port 8001**:
   ```powershell
   cd F:\sqlagent\backend
   python run_port_8001.py
   ```

2. **Update demo.html**:
   - Open `demo_standalone.html` in a text editor
   - Find: `const API_BASE_URL = 'http://localhost:8000';`
   - Change to: `const API_BASE_URL = 'http://localhost:8001';`
   - Save the file

3. **Open the demo page** in your browser

### Option 3: Find and Close the Other Backend Instance

If you have another terminal window with the backend running:
- Go to that terminal
- Press `Ctrl+C` to stop it
- Then start it again in your current terminal

## Check What's Using Port 8000

```powershell
netstat -ano | findstr :8000
```

This shows:
- The process ID (PID) using the port
- Connection status

## Common Causes

1. **Previous backend instance** still running
2. **Another application** using port 8000
3. **Terminal window** with backend still open

## Quick Commands

**Kill process on port 8000:**
```powershell
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

**Use different port:**
```powershell
python run_port_8001.py
# Then update API_BASE_URL in demo_standalone.html to port 8001
```



