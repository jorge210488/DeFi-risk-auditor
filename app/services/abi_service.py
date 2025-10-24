# app/services/abi_service.py
import os
import json
import requests
from typing import Optional, List, Union
from web3 import Web3

from app.models import db
from app.models.contract_abi import ContractABI

# ✅ Etherscan v2: SIEMPRE usar el dominio principal, la red se elige con chainid
ETHERSCAN_V2_BASE = os.getenv("ETHERSCAN_V2_BASE", "https://api.etherscan.io/v2/api")

def _norm_addr(addr: str) -> str:
    if not addr:
        raise ValueError("address vacío")
    return Web3.to_checksum_address(addr)

def get_cached_abi(address: str, network: str = "sepolia") -> Optional[List[dict]]:
    ca = _norm_addr(address)
    rec = ContractABI.query.filter_by(address=ca.lower(), network=network).first()
    return rec.abi if rec else None

def save_abi(address: str, abi: Union[str, List[dict]], network: str = "sepolia", source: str = "manual") -> None:
    # Acepta lista o string JSON
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
        rec = ContractABI(address=ca.lower(), network=network, source=source, abi=abi)
        db.session.add(rec)
    db.session.commit()

def _parse_v2_result(data: dict) -> List[dict]:
    """
    Etherscan v2 puede devolver varias formas:
    - data["result"]["contractInfo"][0]["ABI"] (o "ContractInfo")
    - data["result"][0]["ABI"]
    - Ocasionalmente, "result" puede ser string JSON (fallback).
    """
    res = data.get("result")
    if not res:
        raise RuntimeError(f"Etherscan v2: respuesta sin 'result': {data}")

    # dict con contractInfo / ContractInfo
    if isinstance(res, dict):
        info = res.get("contractInfo") or res.get("ContractInfo")
        if isinstance(info, list) and info:
            abi_str = info[0].get("ABI") or info[0].get("Abi") or info[0].get("abi")
            if not abi_str:
                raise RuntimeError("Etherscan v2: campo ABI vacío")
            abi = json.loads(abi_str)
            if not isinstance(abi, list):
                raise RuntimeError("Etherscan v2: ABI no es lista")
            return abi

    # lista con objetos que tienen ABI
    if isinstance(res, list) and res and isinstance(res[0], dict) and any(k in res[0] for k in ("ABI", "Abi", "abi")):
        abi_str = res[0].get("ABI") or res[0].get("Abi") or res[0].get("abi")
        abi = json.loads(abi_str)
        if not isinstance(abi, list):
            raise RuntimeError("Etherscan v2: ABI no es lista")
        return abi

    # fallback: string JSON
    if isinstance(res, str):
        try:
            abi = json.loads(res)
            if isinstance(abi, list):
                return abi
        except Exception:
            pass

    message = data.get("message") or data.get("Message")
    if str(data.get("status")) == "0" and message:
        raise RuntimeError(f"Etherscan error: {message} — {res}")

    raise RuntimeError(f"No pude parsear la respuesta de Etherscan v2: {data}")

def fetch_abi_from_etherscan(address: str, network: str = "sepolia") -> List[dict]:
    api_key = os.getenv("ETHERSCAN_API_KEY")
    if not api_key:
        raise RuntimeError("ETHERSCAN_API_KEY no definido en el entorno")

    # chainid: de env o por red
    chainid = os.getenv("ETHERSCAN_CHAIN_ID") or os.getenv("WEB3_CHAIN_ID")
    if not chainid:
        chainid = "11155111" if network == "sepolia" else "1"

    params = {
        "module":  "contract",
        "action":  "getabi",
        "address": _norm_addr(address),
        "apikey":  api_key,
        "chainid": chainid,
    }

    # 👇 IMPORTANTE: v2 SIEMPRE en api.etherscan.io/v2/api (no uses subdominios de testnet)
    r = requests.get(ETHERSCAN_V2_BASE, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    # v2 suele devolver status 1/0; 0 con mensaje de error formal
    if str(data.get("status")) == "0":
        raise RuntimeError(f"Etherscan error: {data.get('message')} — {data.get('result')}")

    return _parse_v2_result(data)

def get_or_fetch_abi(address: str, network: str = "sepolia") -> List[dict]:
    abi = get_cached_abi(address, network)
    if abi:
        return abi
    fresh = fetch_abi_from_etherscan(address, network)
    save_abi(address, fresh, network=network, source="etherscan")
    return fresh

# alias usado por el router
get_abi_for_address = get_or_fetch_abi

__all__ = [
    "get_cached_abi",
    "save_abi",
    "fetch_abi_from_etherscan",
    "get_or_fetch_abi",
    "get_abi_for_address",
]
