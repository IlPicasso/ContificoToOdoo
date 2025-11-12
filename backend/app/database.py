"""Database session and engine helpers."""

from importlib.util import find_spec

if find_spec("sqlalchemy") is None:
    raise ModuleNotFoundError(
        "SQLAlchemy no está instalado. Ejecuta `pip install -r backend/requirements.txt` "
        "desde la carpeta del backend antes de iniciar la API."
    )

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Yield a database session and close it afterwards."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
