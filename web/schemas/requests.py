"""API 請求資料格式：欄位、預設值與輸入限制。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    person_slugs: list[str] = Field(default_factory=list)
    person_slug: str = ""  # 舊版單人 API 相容
    title: str = ""
    room_password: str = ""
    allow_guest_join: bool = True


class JoinSessionRequest(BaseModel):
    join_code: str
    password: str = ""
    guest_name: str = ""


class SendMessageRequest(BaseModel):
    content: str = ""
    reply_to: str = Field(
        default="all",
        description="溝通對象：all | user_twin | 名人 person_slug",
    )
    top_k: int | None = Field(
        default=None,
        ge=0,
        le=500,
        description="0 或不傳：依相似度取回全部相關段落；正整數則固定前 N 段",
    )


class DiscussRequest(BaseModel):
    top_k: int | None = Field(default=None, ge=0, le=500)


class TurnRequest(BaseModel):
    top_k: int | None = Field(default=None, ge=0, le=500)


class QueryRequest(BaseModel):
    question: str
    person: str
    top_k: int | None = Field(default=None, ge=0, le=500)
    types: str = ""


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    display_name: str = ""
    initial_preset: str = "life"
    avatar_preset: str = ""


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    bio: str | None = None


class ProfileAvatarPresetRequest(BaseModel):
    avatar_preset: str


class LoginRequest(BaseModel):
    login: str
    password: str


class CreateTwinRequest(BaseModel):
    name: str
    preset: str = "custom"
    bio: str = ""
    twin_context: str = ""


class MarkNotificationsReadRequest(BaseModel):
    session_ids: list[int] = Field(default_factory=list)
    notification_ids: list[int] = Field(default_factory=list)


class PinSessionRequest(BaseModel):
    pinned: bool = True
