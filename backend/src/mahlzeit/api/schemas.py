"""Request and response bodies. Field names are the public API contract."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Language = Literal["de", "en", "nl"]


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorOut(BaseModel):
    code: str
    detail: dict[str, object]


class HealthOut(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]
    version: str


class ConfigOut(BaseModel):
    version: str
    languages: list[Language]
    email_reset: bool
    push_public_key: str | None


class UserOut(Out):
    id: uuid.UUID
    email: str
    display_name: str
    language: Language
    time_zone: str
    is_admin: bool


class ProfileOut(Out):
    show_workouts: bool
    show_body: bool
    share_ai_usage: bool
    start_screen: Literal["today", "list"]
    push_offers: bool


class HouseholdBriefOut(Out):
    id: uuid.UUID
    name: str


class MeOut(BaseModel):
    user: UserOut
    profile: ProfileOut
    household: HouseholdBriefOut
    csrf_token: str


class MemberOut(BaseModel):
    id: uuid.UUID
    display_name: str
    joined_at: datetime
    is_me: bool


class HouseholdOut(BaseModel):
    id: uuid.UUID
    name: str
    members: list[MemberOut]
    max_members: int


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class ResetRequestIn(BaseModel):
    email: str = Field(max_length=254)


class ResetConfirmIn(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(max_length=256)


class MePatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    language: Language | None = None
    time_zone: str | None = Field(default=None, max_length=64)


class ProfilePatch(BaseModel):
    show_workouts: bool | None = None
    show_body: bool | None = None
    share_ai_usage: bool | None = None
    start_screen: Literal["today", "list"] | None = None
    push_offers: bool | None = None


class HouseholdPatch(BaseModel):
    name: str = Field(max_length=200)


class InviteOut(Out):
    id: uuid.UUID
    created_at: datetime
    expires_at: datetime
    note: str | None


class IssuedInviteOut(BaseModel):
    invite: InviteOut
    link: str
    code: str


class InviteCreateIn(BaseModel):
    note: str | None = Field(default=None, max_length=120)


class InvitePreviewOut(BaseModel):
    kind: Literal["household", "partner"]
    status: Literal["pending", "accepted", "revoked", "expired"]
    household_name: str | None
    inviter_name: str | None
    language: Language
    expires_at: datetime


class AcceptInviteIn(BaseModel):
    key: str = Field(max_length=200, description="Link token or the typed code")
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)
    display_name: str = Field(max_length=200)
    language: Language
    time_zone: str = Field(max_length=64)
    household_name: str | None = Field(default=None, max_length=200)


class PushKeys(BaseModel):
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(max_length=2000)
    keys: PushKeys


class PushUnsubscribeIn(BaseModel):
    endpoint: str = Field(max_length=2000)


class PushStatusOut(BaseModel):
    configured: bool
    public_key: str | None
    devices: int


# --- M1: catalogue, day, targets, saved meals --------------------------------------------------

Slot = Literal["breakfast", "lunch", "dinner", "snack"]
DayTypeName = Literal["training", "rest"]


class NutrientsIn(BaseModel):
    kcal: float | None = None
    protein: float | None = None
    carbs: float | None = None
    sugar: float | None = None
    fat: float | None = None
    sat_fat: float | None = None
    fibre: float | None = None
    salt: float | None = None
    alcohol: float | None = None


class ServingIn(BaseModel):
    label: str = Field(max_length=40)
    amount: float


class ItemIn(BaseModel):
    names: dict[Language, str | None]
    brand: str | None = Field(default=None, max_length=80)
    category: Literal[
        "produce",
        "bakery",
        "meat_fish",
        "dairy_eggs",
        "dry_goods",
        "canned",
        "frozen",
        "oils_fats",
        "spices_condiments",
        "sweets_snacks",
        "drinks",
        "household",
        "personal_care",
        "other",
    ] = "other"
    base_unit: Literal["g", "ml"] = "g"
    nutrients: NutrientsIn = Field(default_factory=NutrientsIn)
    package_size: float | None = None
    servings: list[ServingIn] = Field(default_factory=list, max_length=10)
    barcodes: list[str] = Field(default_factory=list, max_length=5)
    tracking_mode: Literal["counted", "status"] = "counted"
    image_url: str | None = Field(default=None, max_length=500)
    source: Literal["custom", "off"] = "custom"


class FavouriteIn(BaseModel):
    on: bool


class ComponentIn(BaseModel):
    item_id: uuid.UUID | None = None
    amount: float | None = None
    serving_label: str | None = Field(default=None, max_length=40)
    serving_count: float | None = None
    quick_name: str | None = Field(default=None, max_length=120)
    kcal: float | None = None
    protein: float | None = None
    carbs: float | None = None
    fat: float | None = None


class EntryIn(BaseModel):
    day: date
    slot: Slot
    at: time | None = None
    name: str | None = Field(default=None, max_length=120)
    eaten_out: bool = False
    components: list[ComponentIn] = Field(default_factory=list, max_length=50)
    saved_meal_id: uuid.UUID | None = None
    portions: float = 1.0


class EntryPatchIn(BaseModel):
    day: date | None = None
    slot: Slot | None = None
    at: time | None = None
    name: str | None = Field(default=None, max_length=120)
    eaten_out: bool | None = None
    components: list[ComponentIn] | None = Field(default=None, max_length=50)


class EntryStateIn(BaseModel):
    state: Literal["planned", "logged", "skipped"]


class CopyEntryIn(BaseModel):
    day: date
    slot: Slot | None = None


class CopyDayIn(BaseModel):
    source_day: date


class TargetsIn(BaseModel):
    kcal: float | None = None
    protein: float | None = None
    carbs: float | None = None
    fat: float | None = None
    day_types: list[DayTypeName] = Field(min_length=1, max_length=2)
    valid_from: date | None = None


class WeekPatternIn(BaseModel):
    pattern: str = Field(max_length=7)


class DayTypeIn(BaseModel):
    day_type: DayTypeName | None


class IngredientIn(BaseModel):
    item_id: uuid.UUID
    amount: float


class SavedMealIn(BaseModel):
    name: str = Field(max_length=120)
    ingredients: list[IngredientIn] = Field(max_length=50)


class SavedMealPatchIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    ingredients: list[IngredientIn] | None = Field(default=None, max_length=50)


class SaveAsMealIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)


# --- shopping list ------------------------------------------------------------------------


class ListFieldsIn(BaseModel):
    """Only the fields that are sent are changed; send null to clear quantity or store."""

    text: str | None = Field(default=None, max_length=200)
    item_id: uuid.UUID | None = None
    quantity: str | None = Field(default=None, max_length=80)
    store_id: uuid.UUID | None = None
    category: str | None = Field(default=None, max_length=20)
    checked: bool | None = None
    parse: bool | None = Field(
        default=None, description="On add: split a quantity such as '2' or '500 g' off the text."
    )


class ListOpIn(BaseModel):
    kind: Literal["add", "update", "remove"]
    id: uuid.UUID = Field(description="The list item's id, made by the client on add.")
    at: datetime | None = Field(default=None, description="When the change was made.")
    fields: ListFieldsIn = Field(default_factory=ListFieldsIn)


class ListOpsIn(BaseModel):
    ops: list[ListOpIn] = Field(max_length=200)


class StoreIn(BaseModel):
    name: str = Field(max_length=80)
