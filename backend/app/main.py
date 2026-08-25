"""Minimal FastAPI entry point for the CityEye AI MVP."""

from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Stable response returned by the health endpoint."""

    status: str
    service: str


app = FastAPI(
    title="CityEye AI Backend",
    description="Local MVP API for reviewed traffic events and citizen reports.",
    version="0.1.0",
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Confirm that the local API process is running."""
    return HealthResponse(status="ok", service="cityeye-ai-backend")
