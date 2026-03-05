import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# On Vercel, the filesystem is read-only except /tmp/
IS_VERCEL = os.getenv("VERCEL", "") == "1"
_default_db = "sqlite:////tmp/attendance.db" if IS_VERCEL else "sqlite:///attendance.db"
DATABASE_URL = os.getenv("DATABASE_URL", _default_db)

# SQLite needs check_same_thread=False; PostgreSQL/Supabase does not
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency to get a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
