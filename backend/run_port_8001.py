"""
Run the backend on port 8001 (if 8000 is busy)
"""
import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print("SQL Agent Backend - Running on PORT 8001")
    print("=" * 60)
    print("If port 8000 is busy, use this script instead.")
    print("Make sure to update demo.html API_BASE_URL to http://localhost:8001")
    print("=" * 60)
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
        log_level="info"
    )



