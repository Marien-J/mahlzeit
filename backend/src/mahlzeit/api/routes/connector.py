from __future__ import annotations

from fastapi import APIRouter, status

from mahlzeit import views
from mahlzeit.api.deps import Current, CurrentWrite, Db
from mahlzeit.services import connector

router = APIRouter(prefix="/connector", tags=["connector"])


@router.get("", response_model=views.ConnectorOut)
def connector_status(current: Current, db: Db) -> views.ConnectorOut:
    row = connector.active(db, current.actor)
    return views.ConnectorOut(
        active=row is not None,
        created_at=row.created_at if row else None,
        last_used_at=row.last_used_at if row else None,
    )


@router.post("", response_model=views.ConnectorCreatedOut, status_code=status.HTTP_201_CREATED)
def create_connector_url(current: CurrentWrite, db: Db) -> views.ConnectorCreatedOut:
    """A new personal URL, shown once. The previous one stops working."""
    return views.ConnectorCreatedOut(url=connector.create(db, current.actor).url)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def revoke_connector_url(current: CurrentWrite, db: Db) -> None:
    connector.revoke(db, current.actor)
