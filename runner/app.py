from fastapi import FastAPI

from . import ai_router, jobs, waha

app = FastAPI(title="Python Runner")

app.include_router(ai_router.router)
app.include_router(waha.router)
app.include_router(jobs.router)
