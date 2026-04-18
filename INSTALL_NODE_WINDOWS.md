# Installing Node.js on Windows

## Method 1: Direct Download (Easiest)

1. **Go to**: https://nodejs.org/
2. **Download**: Click the LTS (Long Term Support) button - it will download a `.msi` file
3. **Run the installer**: Double-click the downloaded file
4. **Follow the wizard**: 
   - Accept license
   - Use default settings
   - Click "Install"
5. **Restart your terminal/PowerShell** after installation
6. **Verify**:
   ```powershell
   node --version
   npm --version
   ```

## Method 2: Using winget (Windows Package Manager)

If you have Windows 10/11 with winget installed:

```powershell
winget install OpenJS.NodeJS.LTS
```

Then restart your terminal and verify:
```powershell
node --version
npm --version
```

## Method 3: Using Chocolatey (If you have it)

If you have Chocolatey package manager installed:

```powershell
choco install nodejs-lts
```

## After Installation

Once Node.js is installed:

1. **Close and reopen your PowerShell/terminal**
2. **Navigate to frontend directory**:
   ```powershell
   cd F:\sqlagent\frontend
   ```
3. **Install dependencies**:
   ```powershell
   npm install
   ```
4. **Run the frontend**:
   ```powershell
   npm run dev
   ```

## Troubleshooting

### If npm is still not recognized:
- **Restart your terminal** (close and reopen PowerShell)
- **Restart your computer** if needed (to refresh environment variables)
- Check if Node.js is in PATH: `$env:PATH` should contain something like `C:\Program Files\nodejs\`

### Verify Installation:
```powershell
# Check Node.js version
node --version

# Check npm version
npm --version

# Check where they're installed
where.exe node
where.exe npm
```



