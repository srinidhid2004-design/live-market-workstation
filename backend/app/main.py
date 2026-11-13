from fastapi import FastAPI

app = FastAPI(title="Live Market Workstation")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}
