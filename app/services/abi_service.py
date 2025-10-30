import os
import json
import requests
from datetime import datetime
from typing import Optional, List, Union

from web3 import Web3

from app.models import db
from app.models.contract_abi import ContractABI

# Base URL for Etherscan v2 API (overridable via env)
ETHERSCAN_V2_BASE = os.getenv("ETHERSCAN_V2_BASE", "https://api.etherscan.io/v2/api")


# ---------------------------
# Normalization helpers
# ---------------------------

def _norm_addr(addr: str) -> str:
    """Normalize an Ethereum address to checksum format (raises on invalid)."""
    if not addr:
        raise ValueError("Empty or invalid contract address")
    return Web3.to_checksum_address(addr)


def _norm_net(net: Optional[str]) -> str:
    """Normalize network name (defaults to 'sepolia')."""
    return (net or "sepolia").strip().lower()


# ---------------------------
# DB cache access
# ---------------------------

def get_cached_abi(address: str, network: str = "sepolia") -> Optional[List[dict]]:
    """
    Return cached ABI (list) for (address, network) or None if missing.
    """
    ca = _norm_addr(address)
    nw = _norm_net(network)
    record = ContractABI.query.filter_by(address=ca.lower(), network=nw).first()
    return record.abi if record else None


def get_cached_record(address: str, network: str = "sepolia") -> Optional[ContractABI]:
    """
    Return cached ContractABI record (with metadata) or None if missing.
    """
    ca = _norm_addr(address)
    nw = _norm_net(network)
    return ContractABI.query.filter_by(address=ca.lower(), network=nw).first()


def save_abi(
    address: str,
    abi: Union[str, List[dict]],
    network: str = "sepolia",
    source: str = "manual",
) -> ContractABI:
    """
    Insert or update ABI for (address, network) and RETURN the DB record.
    Accepts ABI as list[dict] or JSON string; stores address in lowercase.
    """
    if isinstance(abi, str):
        abi = json.loads(abi)
    if not isinstance(abi, list):
        raise RuntimeError("Invalid ABI format: expected a JSON list")

    ca = _norm_addr(address)          # ensure valid checksum (for validation)
    nw = _norm_net(network)
    now = datetime.utcnow()

    rec = ContractABI.query.filter_by(address=ca.lower(), network=nw).first()
    if rec:
        rec.abi = abi
        rec.source = source
        rec.updated_at = now
    else:
        rec = ContractABI(
            address=ca.lower(),
            network=nw,
            source=source,
            abi=abi,
            created_at=now,
            updated_at=now,
        )
        db.session.add(rec)

    db.session.commit()
    return rec


# ---------------------------
# Etherscan v2 parsing/fetch
# ---------------------------

def _parse_v2_result(data: dict) -> List[dict]:
    """
    Parse Etherscan v2 response and return ABI as list[dict].

    Etherscan v2 may return:
      - data["result"]["contractInfo"][0]["ABI"] (or "ContractInfo")
      - data["result"][0]["ABI"]
      - data["result"] as a JSON string (fallback)
    """
    res = data.get("result")
    if not res:
        raise RuntimeError(f"Etherscan v2: missing 'result': {data}")

    # Case 1: dict with contractInfo/ContractInfo -> list -> first -> ABI/Abi/abi (string)
    if isinstance(res, dict):
        info_list = res.get("contractInfo") or res.get("ContractInfo")
        if isinstance(info_list, list) and info_list:
            abi_str = info_list[0].get("ABI") or info_list[0].get("Abi") or info_list[0].get("abi")
            if not abi_str:
                raise RuntimeError("Etherscan v2: empty ABI field in response")
            abi = json.loads(abi_str)
            if not isinstance(abi, list):
                raise RuntimeError("Etherscan v2: parsed ABI is not a list")
            return abi

    # Case 2: list of dicts with ABI/Abi/abi key (string)
    if isinstance(res, list) and res and isinstance(res[0], dict) and any(k in res[0] for k in ("ABI", "Abi", "abi")):
        abi_str = res[0].get("ABI") or res[0].get("Abi") or res[0].get("abi")
        abi = json.loads(abi_str)
        if not isinstance(abi, list):
            raise RuntimeError("Etherscan v2: parsed ABI is not a list")
        return abi

    # Case 3: result is a JSON string
    if isinstance(res, str):
        try:
            abi = json.loads(res)
            if isinstance(abi, list):
                return abi
        except json.JSONDecodeError:
            pass

    # If Etherscan returned status=0 with an error message, bubble it up
    message = data.get("message") or data.get("Message")
    if str(data.get("status")) == "0" and message:
        raise RuntimeError(f"Etherscan error: {message} — {res}")

    raise RuntimeError(f"Could not interpret Etherscan v2 response: {data}")


def fetch_abi_from_etherscan(address: str, network: str = "sepolia") -> List[dict]:
    """
    Fetch ABI from Etherscan v2 (requires ETHERSCAN_API_KEY).
    """
    api_key = os.getenv("ETHERSCAN_API_KEY")
    if not api_key:
        raise RuntimeError("ETHERSCAN_API_KEY is not set")

    nw = _norm_net(network)

    # Resolve chainid: prefer ETHERSCAN_CHAIN_ID or WEB3_CHAIN_ID; fallback by network
    chainid = os.getenv("ETHERSCAN_CHAIN_ID") or os.getenv("WEB3_CHAIN_ID")
    if not chainid:
        chainid = "11155111" if nw == "sepolia" else "1"  # Sepolia=11155111, Mainnet=1, etc.

    params = {
        "module": "contract",
        "action": "getabi",
        "address": _norm_addr(address),
        "apikey": api_key,
        "chainid": chainid,
    }

    resp = requests.get(ETHERSCAN_V2_BASE, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    if str(data.get("status")) == "0":
        raise RuntimeError(f"Etherscan error: {data.get('message')} — {data.get('result')}")

    return _parse_v2_result(data)


# ---------------------------
# High-level getters
# ---------------------------

def get_or_fetch_abi(address: str, network: str = "sepolia") -> List[dict]:
    """
    Return ABI list for (address, network), using DB as cache and
    fetching from Etherscan if missing (then persist as 'etherscan').
    """
    nw = _norm_net(network)
    cached = get_cached_abi(address, nw)
    if cached:
        return cached
    fresh_abi = fetch_abi_from_etherscan(address, nw)
    save_abi(address, fresh_abi, network=nw, source="etherscan")
    return fresh_abi


def get_or_fetch_record(address: str, network: str = "sepolia") -> ContractABI:
    """
    Return ContractABI record with metadata; fetch + persist if missing.
    """
    nw = _norm_net(network)
    rec = get_cached_record(address, nw)
    if rec:
        return rec
    fresh_abi = fetch_abi_from_etherscan(address, nw)
    return save_abi(address, fresh_abi, network=nw, source="etherscan")


# Backward-compatible alias (routes may import this)
get_abi_for_address = get_or_fetch_abi
