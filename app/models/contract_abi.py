from datetime import datetime
from app.models import db
from app.models.types import JSONBCompat

class ContractABI(db.Model):
    __tablename__ = "contract_abis"

    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(42), nullable=False)       # Dirección del contrato (checksum en minúsculas)
    network = db.Column(db.String(32), nullable=False, default="sepolia")  # Red (ej. sepolia, mainnet, etc.)
    source  = db.Column(db.String(32), nullable=True)        # Origen de la ABI: 'etherscan', 'manual', etc.
    abi     = db.Column(JSONBCompat(), nullable=False)       # ABI almacenada en formato JSON

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("address", "network", name="uq_contract_abis_address_network"),  # UNIQUE compuesto
        db.Index("ix_contract_abis_address", "address"),
        db.Index("ix_contract_abis_network", "network"),
    )
