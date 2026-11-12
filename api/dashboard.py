from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def mount_dashboard(app: FastAPI, directory: Path) -> None:
    """Mount last, after API/WebSocket routes, for a single local kiosk origin."""
    if not (directory / 'index.html').is_file():
        raise RuntimeError('Dashboard build missing. Run npm ci and npm run build in frontend/.')
    app.mount('/', StaticFiles(directory=directory, html=True), name='dashboard')
