from contextlib import asynccontextmanager

from fastapi import FastAPI

from cv_evaluator.api.routes import router
from cv_evaluator.services.embeddings import initialize_embeddings


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_embeddings()
    yield


app = FastAPI(
    title="CV Evaluator",
    description="Job Fit & Salary Estimator API",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
