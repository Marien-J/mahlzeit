"""ASGI entry point: `uvicorn mahlzeit.main:app`."""

from mahlzeit.api.app import create_app

app = create_app()
