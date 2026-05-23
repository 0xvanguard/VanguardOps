"""User CRUD operations (authentication + management)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.crud.base import CRUDBase
from app.models.user import User
from app.schemas.auth import UserCreate, UserUpdate


class CRUDUser(CRUDBase[User, UserCreate, UserUpdate]):
    def get_by_email(self, db: Session, *, email: str) -> User | None:
        stmt = select(User).where(User.email == email.lower())
        return db.execute(stmt).scalar_one_or_none()

    def create(self, db: Session, *, obj_in: UserCreate | dict) -> User:  # type: ignore[override]
        data = obj_in.copy() if isinstance(obj_in, dict) else obj_in.model_dump()
        password = data.pop("password")
        data["email"] = data["email"].lower()
        db_user = User(**data, hashed_password=hash_password(password))
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

    def update(  # type: ignore[override]
        self,
        db: Session,
        *,
        db_obj: User,
        obj_in: UserUpdate | dict,
    ) -> User:
        if isinstance(obj_in, dict):
            update_data = {k: v for k, v in obj_in.items() if v is not None}
        else:
            update_data = obj_in.model_dump(exclude_unset=True)

        if "password" in update_data:
            db_obj.hashed_password = hash_password(update_data.pop("password"))

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj


user = CRUDUser(User)
