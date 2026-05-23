"""Generic CRUD repository used as a base for every domain repository.

Design notes
------------
* ``create`` does **not** roundtrip through :func:`fastapi.encoders.jsonable_encoder`.
  Doing so would coerce ``datetime`` values into ISO-8601 strings, which the
  SQLAlchemy SQLite driver rejects (and PostgreSQL only tolerates with implicit
  casts). Instead we use Pydantic's ``model_dump()`` directly, preserving the
  native Python types.
* ``count`` is provided for paginated endpoints to compute ``has_next`` /
  ``has_prev`` without a second query in client code.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import Base

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class CRUDBase[ModelType: Base, CreateSchemaType: BaseModel, UpdateSchemaType: BaseModel]:
    """Default Create/Read/Update/Delete operations for a single model."""

    def __init__(self, model: type[ModelType]) -> None:
        self.model = model

    # --- Read -----------------------------------------------------------

    def get(self, db: Session, id: Any) -> ModelType | None:
        return db.get(self.model, id)

    def get_multi(self, db: Session, *, skip: int = 0, limit: int = 100) -> Sequence[ModelType]:
        stmt = select(self.model).offset(skip).limit(limit)
        return db.execute(stmt).scalars().all()

    def count(self, db: Session) -> int:
        stmt = select(func.count()).select_from(self.model)
        return int(db.execute(stmt).scalar_one())

    # --- Write ----------------------------------------------------------

    def create(self, db: Session, *, obj_in: CreateSchemaType | dict[str, Any]) -> ModelType:
        if isinstance(obj_in, BaseModel):
            data = obj_in.model_dump(exclude_unset=False)
        else:
            data = dict(obj_in)
        db_obj = self.model(**data)  # type: ignore[arg-type]
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(
        self,
        db: Session,
        *,
        db_obj: ModelType,
        obj_in: UpdateSchemaType | dict[str, Any],
    ) -> ModelType:
        if isinstance(obj_in, BaseModel):
            update_data = obj_in.model_dump(exclude_unset=True)
        else:
            update_data = {k: v for k, v in obj_in.items() if v is not None}

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def remove(self, db: Session, *, id: Any) -> ModelType | None:
        obj = db.get(self.model, id)
        if obj is None:
            return None
        db.delete(obj)
        db.commit()
        return obj
