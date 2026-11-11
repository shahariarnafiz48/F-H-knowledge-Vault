"""Vercel entry point: exposes the FastAPI application. All routes are rewritten here by vercel.json."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from app.main import app   # noqa: E402,F401
