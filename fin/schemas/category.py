from pydantic import BaseModel, Field


class CategoryCreate(BaseModel):
    direction: str = Field(pattern="^(income|expense)$")
    name: str = Field(min_length=1, max_length=20)
    bg_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    text_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=20)
    bg_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    text_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


class CategoryResponse(BaseModel):
    id: str
    direction: str
    name: str
    bg_color: str
    text_color: str
    is_builtin: bool
    status: str = "Y"
    sort_order: int = 0
