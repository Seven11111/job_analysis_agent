"""Non-secret local settings endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/settings", tags=["settings"])
