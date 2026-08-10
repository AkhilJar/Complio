from fastapi import FastAPI

from api.routes import documents, health

app = FastAPI(title="Complio API")
app.include_router(health.router)
app.include_router(documents.router)
