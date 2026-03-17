from fastapi import FastAPI

from app.routers.clusters import router as clusters_router
from app.routers.digest import router as digest_router
from app.routers.items import router as items_router

app = FastAPI(title="Insight", version="0.1.0")
app.include_router(items_router)
app.include_router(digest_router)
app.include_router(clusters_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
