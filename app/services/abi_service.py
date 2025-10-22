# app/services/abi_service.py
import os
import json
import requests
from typing import Optional, List, Union
from web3 import Web3

from app.models import db
from app.models.contract_abi import ContractABI

# Endpoints base de Etherscan (agrega otros si usas más redes)
_ETHERSCAN_BASES = {
    "sepolia":  "https://api-sepolia.etherscan.io/api",
    "mainnet":  "https://api.etherscan.io/api",
    "ethereum": "https://api.etherscan.io/api",
}

def _norm_addr(addr: str) -> str:
    if not addr:
        raise ValueError("address vacío")
    # Web3 v6: normalizamos chequeando checksum
    return Web3.to_checksum_address(addr)

def get_cached_abi(address: str, network: str = "sepolia") -> Optional[List[dict]]:
    """
    Busca el ABI en caché (tabla contract_abis). Devuelve lista (ABI) o None.
    """
    ca = _norm_addr(address)
    rec = ContractABI.query.filter_by(address=ca.lower(), network=network).first()
    return rec.abi if rec else None

def save_abi(address: str, abi: Union[str, List[dict]], network: str = "sepolia", source: str = "manual") -> None:
    """
    Guarda/actualiza el ABI en la tabla contract_abis.
    Acepta abi como lista o string JSON.
    """
    if isinstance(abi, str):
        abi = json.loads(abi)
    if not isinstance(abi, list):
        raise RuntimeError("Formato de ABI inválido: se esperaba lista")

    ca = _norm_addr(address)
    rec = ContractABI.query.filter_by(address=ca.lower(), network=network).first()
    if rec:
        rec.abi = abi
        rec.source = source
    else:
        rec = ContractABI(
            address=ca.lower(),
            network=network,
            source=source,
            abi=abi,
        )
        db.session.add(rec)
    db.session.commit()

def fetch_abi_from_etherscan(address: str, network: str = "sepolia") -> List[dict]:
    """
    Descarga el ABI desde Etherscan. Requiere ETHERSCAN_API_KEY.
    """
    api_key = os.getenv("ETHERSCAN_API_KEY")
    if not api_key:
        raise RuntimeError("ETHERSCAN_API_KEY no definido en el entorno")

    base = _ETHERSCAN_BASES.get(network, _ETHERSCAN_BASES["sepolia"])
    params = {
        "module":  "contract",
        "action":  "getabi",
        "address": _norm_addr(address),
        "apikey":  api_key,
    }
    r = requests.get(base, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    if str(data.get("status")) != "1":
        raise RuntimeError(f"Etherscan error: {data.get('message')} — {data.get('result')}")
    abi = json.loads(data["result"])
    if not isinstance(abi, list):
        raise RuntimeError("Formato ABI inesperado desde Etherscan")
    return abi

def get_or_fetch_abi(address: str, network: str = "sepolia") -> List[dict]:
    """
    Retorna ABI desde caché si existe; si no, lo baja de Etherscan y lo guarda.
    """
    abi = get_cached_abi(address, network)
    if abi:
        return abi
    fresh = fetch_abi_from_etherscan(address, network)
    save_abi(address, fresh, network=network, source="etherscan")
    return fresh

# 🔑 alias para que el router pueda importar este nombre
get_abi_for_address = get_or_fetch_abi

__all__ = [
    "get_cached_abi",
    "save_abi",
    "fetch_abi_from_etherscan",
    "get_or_fetch_abi",
    "get_abi_for_address",
]
