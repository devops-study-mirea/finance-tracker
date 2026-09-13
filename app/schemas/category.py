from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.category import CategoryKind
from app.palette import SLOT_COUNT, slot_hex

ColorSlot = Field(ge=0, lt=SLOT_COUNT, description="Номер слота палитры, см. app/palette.py")


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: CategoryKind
    parent_id: int | None = None
    color_slot: int = Field(default=0, ge=0, lt=SLOT_COUNT)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    parent_id: int | None = None
    color_slot: int | None = Field(default=None, ge=0, lt=SLOT_COUNT)
    is_archived: bool | None = None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: CategoryKind
    parent_id: int | None
    color_slot: int
    is_archived: bool

    @computed_field  # type: ignore[prop-decorator]
    @property
    def color(self) -> str:
        """Готовый hex для светлой темы — чтобы внешним клиентам API
        не приходилось знать про устройство палитры."""
        return slot_hex(self.color_slot)
