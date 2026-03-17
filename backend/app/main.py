from fastapi import FastAPI

from app.routers.items import router as items_router

app = FastAPI(title="Insight", version="0.1.0")
app.include_router(items_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
