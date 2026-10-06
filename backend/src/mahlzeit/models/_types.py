from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from sqlalchemy import DateTime, Uuid
from sqlalchemy.orm import mapped_column

from mahlzeit import clock
from mahlzeit.ids import uuid7

UuidPk = Annotated[uuid.UUID, mapped_column(Uuid, primary_key=True, default=uuid7)]
Timestamp = Annotated[datetime, mapped_column(DateTime(timezone=True), default=clock.now)]
OptTimestamp = Annotated[datetime | None, mapped_column(DateTime(timezone=True))]
