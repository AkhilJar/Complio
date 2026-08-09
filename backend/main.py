from fastapi import FastAPI

from api.routes import health

app = FastAPI(title="Complio API")
app.include_router(health.router)