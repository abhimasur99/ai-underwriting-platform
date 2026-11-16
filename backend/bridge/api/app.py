"""FastAPI app. Routes arrive in Sprint 2."""
from fastapi import FastAPI

app = FastAPI(title="Bridge Loan Platform (sample data only)")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
