"""Version 1 API router."""

from fastapi import APIRouter

from api.v1.endpoints.health import router as health_router
from api.v1.endpoints.jobs import router as jobs_router
from api.v1.endpoints.applications import router as applications_router
from api.v1.endpoints.profile import router as profile_router
from api.v1.endpoints.providers import router as providers_router
from api.v1.endpoints.matches import router as matches_router
from api.v1.endpoints.agent import router as agent_router
from api.v1.endpoints.campus_recruit import router as campus_recruit_router

router = APIRouter()
router.include_router(health_router)
router.include_router(jobs_router)
router.include_router(applications_router)
router.include_router(profile_router)
router.include_router(providers_router)
router.include_router(matches_router)
router.include_router(agent_router)
router.include_router(campus_recruit_router)
