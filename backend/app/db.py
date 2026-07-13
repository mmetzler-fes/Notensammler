"""SQLAlchemy-Modelle und Session-Handling.

Die Datenbank wird über ``DATABASE_URL`` konfiguriert. Standard ist eine
SQLite-Datei; ein späterer Wechsel auf PostgreSQL ist damit reine Konfiguration.
"""
from __future__ import annotations

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


class Klasse(Base):
    __tablename__ = "klassen"

    klasse = Column(String, primary_key=True)
    klassenlehrer = Column(String, nullable=False)


class Deputat(Base):
    """Eine Zeile der Deputats-Rohdaten (eine Unterrichtsstunde im Stundenplan)."""

    __tablename__ = "deputat"

    eintrag = Column(Integer, primary_key=True, autoincrement=True)
    lehrerkuerzel = Column(String, nullable=False, index=True)
    klasse = Column(String, ForeignKey("klassen.klasse"), nullable=False, index=True)
    gruppe = Column(String, nullable=False, default="")
    fach = Column(String, nullable=False)
    deputat = Column(String, nullable=False)  # Kennung, z. B. "B22", "BLO1"
    stunden = Column(Integer, nullable=False, default=1)


class Notenblatt(Base):
    """Eine Notenspalte im Notenblatt einer Klasse (je Halbjahr)."""

    __tablename__ = "notenblatt"

    eintrag = Column(Integer, primary_key=True, autoincrement=True)
    kategorie = Column(String, nullable=False)  # BFK, PK, Verhalten, Mitarbeit
    klasse = Column(String, ForeignKey("klassen.klasse"), nullable=False, index=True)
    gruppe = Column(String, nullable=False, default="")
    halbjahr = Column(Integer, nullable=False)  # 1 oder 2
    lehrerkuerzel = Column(String, nullable=False)
    fach = Column(String, nullable=False)
    gewichtung = Column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "kategorie", "klasse", "gruppe", "halbjahr", "lehrerkuerzel", "fach",
            name="uq_notenblatt_spalte",
        ),
    )


class Schueler(Base):
    __tablename__ = "schueler"

    schuelerid = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    vorname = Column(String, nullable=False)
    klasse = Column(String, ForeignKey("klassen.klasse"), nullable=False, index=True)


class Noteneintrag(Base):
    """Note eines Lehrers für einen Schüler in einer Notenblatt-Spalte."""

    __tablename__ = "noteneintrag"

    eintrag_id = Column(Integer, primary_key=True, autoincrement=True)
    schuelerid = Column(Integer, ForeignKey("schueler.schuelerid"), nullable=False, index=True)
    notenblatt_id = Column(Integer, ForeignKey("notenblatt.eintrag"), nullable=False, index=True)
    lehrer = Column(String, nullable=False)
    note = Column(Numeric(3, 1), nullable=True)

    __table_args__ = (
        UniqueConstraint("schuelerid", "notenblatt_id", name="uq_note_je_spalte"),
    )


def make_engine(url: str | None = None):
    url = url or settings.DATABASE_URL
    kwargs = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):
        # WAL + Fremdschlüssel: nebenläufige Lesezugriffe blockieren nicht.
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _rec):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


def make_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, future=True)


def init_db(engine):
    Base.metadata.create_all(engine)
