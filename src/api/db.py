"""Base de données (SQLite par défaut) : le catalogue constructeurs.

SQLAlchemy permet de passer à PostgreSQL plus tard en changeant seulement l'URL de connexion
(variable d'environnement PFE_DB_URL). Par défaut : fichier data/app.db (ignoré par Git).
Les prix et les fournisseurs viendront plus tard, avec le chiffrage.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Equipment(Base):
    """Une référence de matériel du catalogue."""

    __tablename__ = "equipements"
    __table_args__ = (UniqueConstraint("fabricant", "reference", name="uq_fabricant_reference"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    famille: Mapped[str] = mapped_column(String(60), default="")
    fabricant: Mapped[str] = mapped_column(String(120), default="")
    reference: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(String(500), default="")
    unite: Mapped[str] = mapped_column(String(4), default="u")
    source: Mapped[str] = mapped_column(String(20), default="saisie")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


def make_session_factory(url):
    """Crée les tables si besoin et renvoie une fabrique de sessions."""
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)