"""SQLAlchemy tables. Import every model here so Alembic sees them."""

from mahlzeit.models.accounts import (
    AuthSession,
    Household,
    Invite,
    LoginAttempt,
    PasswordReset,
    Profile,
    User,
)
from mahlzeit.models.audit import ChangeRecord
from mahlzeit.models.catalogue import (
    Favourite,
    Item,
    ItemBarcode,
    Recipe,
    RecipeIngredient,
    ServingSize,
)
from mahlzeit.models.connector import ConnectorToken, OffCache, RateWindow
from mahlzeit.models.day import (
    DayTypeOverride,
    MealComponent,
    MealEntry,
    MealParticipant,
    TargetSet,
)
from mahlzeit.models.jobs import Job
from mahlzeit.models.push import PushSubscription

__all__ = [
    "AuthSession",
    "ChangeRecord",
    "ConnectorToken",
    "DayTypeOverride",
    "Favourite",
    "Household",
    "Invite",
    "Item",
    "ItemBarcode",
    "Job",
    "LoginAttempt",
    "MealComponent",
    "MealEntry",
    "MealParticipant",
    "OffCache",
    "PasswordReset",
    "Profile",
    "PushSubscription",
    "RateWindow",
    "Recipe",
    "RecipeIngredient",
    "ServingSize",
    "TargetSet",
    "User",
]
