# app/models/types.py
from sqlalchemy.types import TypeDecorator
from sqlalchemy import JSON

class JSONBCompat(TypeDecorator):
    """
    JSONB en PostgreSQL, JSON genérico en SQLite y otros.
    Permite que los mismos modelos funcionen en tests (sqlite://)
    y en producción (postgresql://).
    """
    impl = JSON
    cache_ok = True

    def __init__(self, **jsonb_kwargs):
        # Aceptamos kwargs para JSONB por si deseas usarlos en futuro
        super().__init__()
        self._jsonb_kwargs = jsonb_kwargs

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            # Usar JSONB nativo si estamos en Postgres
            from sqlalchemy.dialects.postgresql import JSONB
            return dialect.type_descriptor(JSONB(**self._jsonb_kwargs))
        # En SQLite / otros, usar JSON genérico
        return dialect.type_descriptor(JSON())
