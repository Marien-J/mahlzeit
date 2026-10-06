from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from mahlzeit import __version__
from mahlzeit.api.deps import Db
from mahlzeit.api.schemas import ConfigOut, HealthOut
from mahlzeit.config import get_settings
from mahlzeit.domain.accounts import LANGUAGES

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthOut)
def health(db: Db) -> HealthOut:
    db.execute(text("SELECT 1"))
    return HealthOut(status="ok", database="ok", version=__version__)


@router.get("/config", response_model=ConfigOut)
def config() -> ConfigOut:
    s = get_settings()
    return ConfigOut(
        version=__version__,
        languages=list(LANGUAGES),
        email_reset=s.email_enabled,
        push_public_key=s.vapid_public_key if s.push_enabled else None,
    )
