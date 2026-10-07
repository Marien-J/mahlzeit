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
    ExactAmount,
    MealComponent,
    MealEntry,
    MealParticipant,
    Offer,
    TargetSet,
)
from mahlzeit.models.jobs import Job
from mahlzeit.models.push import PushSubscription
from mahlzeit.models.shopping import ListMemory, ShoppingListItem, Store

__all__ = [
    "AuthSession",
    "ChangeRecord",
    "ConnectorToken",
    "DayTypeOverride",
    "ExactAmount",
    "Favourite",
    "Household",
    "Invite",
    "Item",
    "ItemBarcode",
    "Job",
    "ListMemory",
    "LoginAttempt",
    "MealComponent",
    "MealEntry",
    "MealParticipant",
    "OffCache",
    "Offer",
    "PasswordReset",
    "Profile",
    "PushSubscription",
    "RateWindow",
    "Recipe",
    "RecipeIngredient",
    "ServingSize",
    "ShoppingListItem",
    "Store",
    "TargetSet",
    "User",
]
