# Streamlit Frontend Setup

## Quick Start

### 1. Install Streamlit (if not already installed)

```powershell
pip install streamlit requests pandas
```

Or install from requirements:
```powershell
cd frontend_streamlit
pip install -r requirements.txt
```

### 2. Start the Backend

In one terminal:
```powershell
cd F:\sqlagent\backend
python run.py
```

### 3. Start Streamlit Frontend

In another terminal:
```powershell
cd F:\sqlagent\frontend_streamlit
streamlit run app.py
```

Streamlit will automatically open in your browser at `http://localhost:8501`

## Usage

1. **Connect to Database**:
   - Enter your server, database, username
   - Leave password empty for Azure AD MFA
   - Check "Use Azure AD MFA"
   - Click "Connect to Database"
   - A browser window will open for Azure AD authentication

2. **Query Database**:
   - **Natural Language Tab**: Type questions in plain English
   - **Raw SQL Tab**: Write and execute SQL directly

3. **Download Results**: Click download buttons to save as CSV or JSON

## Features

✅ Clean, modern interface  
✅ Natural language to SQL conversion  
✅ Direct SQL execution  
✅ Results displayed in tables  
✅ CSV/JSON download  
✅ Azure AD MFA support  

## Alternative: HTML Version (No Installation)

If you prefer not to install Streamlit, you can still use `demo_standalone.html`:
- Just open it in your browser
- No installation needed
- Works with the same backend



