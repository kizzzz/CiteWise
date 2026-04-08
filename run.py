"""CiteWise V3 启动入口"""
import os
import uvicorn

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "10000"))
    reload = os.getenv("RELOAD", "false").lower() == "true"
    uvicorn.run("api.main:app", host=host, port=port, reload=reload)
