from fastapi import FastAPI

from graph import db

app = FastAPI(title="KT Brain")


@app.get("/api/health")
def health():
    return {"ok": True, "graphs": db.list_graphs()}
