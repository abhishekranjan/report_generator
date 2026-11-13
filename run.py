"""Start the report generator:  python run.py"""
import os

import uvicorn

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    print(f"Report generator running at http://{host}:{port}")
    uvicorn.run("app.main:app", host=host, port=port)
