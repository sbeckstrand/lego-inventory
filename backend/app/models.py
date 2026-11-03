from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Condition(str, enum.Enum):
    NEW = "New"
    LIKE_NEW = "Like New"
    MODERATE = "Moderate"
    POOR = "Poor"


class Status(str, enum.Enum):
    IN_BOX = "In box"
    IN_BAGS = "In bags"
    ASSEMBLED = "Assembled"


class CatalogSet(Base):
    """API-derived data about a set *design*, shared by every owned copy.

    Keyed by the Rebrickable set number (e.g. ``75192-1``). Cached so the app
    keeps working (and stays fast) without hitting the API on every page view.
    """

    __tablename__ = "catalog_set"

    set_num: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_parts: Mapped[int] = mapped_column(Integer, default=0)
    theme_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Top-level (root) theme name, e.g. "Star Wars", "Harry Potter", "Icons".
    theme: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    parts: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    minifigs: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    owned: Mapped[list["OwnedSet"]] = relationship(back_populates="catalog")


class OwnedSet(Base):
    """A physical set you own. You can own several copies of the same set_num."""

    __tablename__ = "owned_set"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_num: Mapped[str] = mapped_column(ForeignKey("catalog_set.set_num"), index=True)
    purchased_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    storage_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    condition: Mapped[str] = mapped_column(String(32), default=Condition.NEW.value)
    status: Mapped[str] = mapped_column(String(32), default=Status.IN_BOX.value)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    catalog: Mapped["CatalogSet"] = relationship(back_populates="owned")


class Part(Base):
    """A distinct part, identified by part number + color."""

    __tablename__ = "part"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    part_num: Mapped[str] = mapped_column(String(32), index=True)
    color_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    color_name: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    img_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    __table_args__ = (
        UniqueConstraint("part_num", "color_name", name="uq_part_num_color"),
    )


class SetPart(Base):
    """One line of a set's part inventory, materialised for aggregation."""

    __tablename__ = "set_part"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_num: Mapped[str] = mapped_column(
        ForeignKey("catalog_set.set_num", ondelete="CASCADE"), index=True
    )
    part_id: Mapped[int] = mapped_column(
        ForeignKey("part.id", ondelete="CASCADE"), index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    is_spare: Mapped[bool] = mapped_column(Boolean, default=False)


class LoosePart(Base):
    """Parts you own that are NOT part of a set (added independently)."""

    __tablename__ = "loose_part"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    part_id: Mapped[int] = mapped_column(
        ForeignKey("part.id", ondelete="CASCADE"), unique=True, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    part: Mapped["Part"] = relationship()


class Minifig(Base):
    """A distinct minifigure, identified by its Rebrickable fig number."""

    __tablename__ = "minifig"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fig_num: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    img_url: Mapped[str | None] = mapped_column(String(512), nullable=True)


class SetMinifig(Base):
    """One line of a set's minifig inventory, materialised for aggregation."""

    __tablename__ = "set_minifig"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_num: Mapped[str] = mapped_column(
        ForeignKey("catalog_set.set_num", ondelete="CASCADE"), index=True
    )
    minifig_id: Mapped[int] = mapped_column(
        ForeignKey("minifig.id", ondelete="CASCADE"), index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, default=0)


class LooseMinifig(Base):
    """Minifigs you own that are NOT part of a set (added independently)."""

    __tablename__ = "loose_minifig"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    minifig_id: Mapped[int] = mapped_column(
        ForeignKey("minifig.id", ondelete="CASCADE"), unique=True, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    minifig: Mapped["Minifig"] = relationship()
