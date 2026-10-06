"""Request and response bodies. Field names are the public API contract."""

from __future__ import annotations

import uuid
from datetime import datetime
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
