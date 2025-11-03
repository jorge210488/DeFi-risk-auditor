# app/services/blockchain_service.py
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from web3 import Web3

ABIType = Union[List[dict], dict]


def _build_w3() -> Web3:
    provider = os.getenv("WEB3_PROVIDER_URI")
    if not provider:
        raise RuntimeError("WEB3_PROVIDER_URI no configurado")

    w3 = Web3(Web3.HTTPProvider(provider, request_kwargs={"timeout": 15}))

    # PoA (Sepolia, etc.)
    use_poa = os.getenv("WEB3_USE_POA", "false").lower() in ("1", "true", "yes", "on")
    if use_poa:
        try:
            from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware
            w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        except Exception:
            from web3.middleware.geth_poa import geth_poa_middleware
            w3.middleware_onion.inject(geth_poa_middleware, layer=0)

    if not w3.is_connected():
        raise RuntimeError("No se pudo conectar a la RPC")
    return w3


def _normalize_value(v: Any) -> int:
    if isinstance(v, str):
        return int(v, 0)  # "10" o "0x..."
    return int(v or 0)


def _resolve_abi(
    contract_address: str,
    *,
    abi_inline: Optional[ABIType] = None,
    abi_path: Optional[str] = None,
    network: str = "sepolia",
    force_refresh: bool = False,
    cache_manual: bool = False,
) -> ABIType:
    """
    Prioridad:
      1) abi_inline
      2) abi_path (archivo)
      3) force_refresh (Etherscan + cache)
      4) cache en DB (get_or_fetch_record → DB o Etherscan)
      5) archivo default de ENV (si existe)
    """
    # Import tardío para evitar ciclos
    from app.services.abi_service import (
        get_cached_record,
        get_or_fetch_record,
        fetch_abi_from_etherscan,
        save_abi,
    )

    if abi_inline is not None:
        abi = json.loads(abi_inline) if isinstance(abi_inline, str) else abi_inline
        if cache_manual:
            save_abi(contract_address, abi, network=network, source="manual")
        return abi

    if abi_path:
        p = Path(abi_path)
        if not p.exists():
            raise FileNotFoundError(f"ABI no encontrado en abi_path: {abi_path}")
        return json.loads(p.read_text(encoding="utf-8"))

    if force_refresh:
        fresh = fetch_abi_from_etherscan(contract_address, network=network)
        rec = save_abi(contract_address, fresh, network=network, source="etherscan")
        return rec.abi

    rec = get_cached_record(contract_address, network)
    if rec:
        return rec.abi

    rec = get_or_fetch_record(contract_address, network)
    if rec and rec.abi:
        return rec.abi

    # Último fallback: ENV path
    env_path = os.getenv("CONTRACT_ABI_PATH")
    if env_path and Path(env_path).exists():
        return json.loads(Path(env_path).read_text(encoding="utf-8"))

    raise RuntimeError("No se pudo resolver ABI (ni inline, ni archivo, ni Etherscan/DB).")


def _load_contract(
    w3: Web3,
    *,
    contract_address: Optional[str],
    overrides: Optional[Dict[str, Any]] = None,
):
    addr = (contract_address or os.getenv("CONTRACT_ADDRESS") or "").strip()
    if not addr:
        raise RuntimeError("CONTRACT_ADDRESS no configurado (ni en overrides ni en ENV)")

    ov = overrides or {}
    network = (ov.get("network") or os.getenv("ETHERSCAN_NETWORK", "sepolia")).strip().lower()
    abi = _resolve_abi(
        addr,
        abi_inline=ov.get("abi"),
        abi_path=ov.get("abi_path"),
        network=network,
        force_refresh=bool(ov.get("force_refresh", False)),
        cache_manual=bool(ov.get("cache_manual", False)),
    )

    return w3.eth.contract(address=Web3.to_checksum_address(addr), abi=abi)


def call_function(fn_name: str, *args, value: int = 0, overrides: Optional[Dict[str, Any]] = None):
    """Lectura (view/pure) — no gasta gas."""
    w3 = _build_w3()
    contract = _load_contract(w3, contract_address=overrides.get("contract_address") if overrides else None, overrides=overrides)
    if not hasattr(contract.functions, fn_name):
        raise ValueError(f"Función '{fn_name}' no existe en ABI del contrato {contract.address}")
    fn = getattr(contract.functions, fn_name)(*args)
    return fn.call({"value": _normalize_value(value)})


def send_function(
    fn_name: str,
    *args,
    value: int = 0,
    overrides: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Escritura — firma y envía transacción. Devuelve tx_hash (hex).
    Usa overrides para address/ABI/network/force_refresh/cache_manual.
    """
    from web3.exceptions import ContractCustomError

    w3 = _build_w3()
    contract = _load_contract(w3, contract_address=overrides.get("contract_address") if overrides else None, overrides=overrides)

    if not hasattr(contract.functions, fn_name):
        # Lista funciones disponibles para debugar
        fns = sorted(set(dir(contract.functions)) - set(dir(object())))
        raise ValueError(f"La función '{fn_name}' no existe en el ABI del contrato {contract.address}. Disponibles (parcial): {fns[:20]}")

    private_key = os.getenv("PRIVATE_KEY")
    if not private_key:
        raise RuntimeError("PRIVATE_KEY no configurada")

    account = w3.eth.account.from_key(private_key)
    chain_id = int(os.getenv("WEB3_CHAIN_ID") or w3.eth.chain_id)

    v_wei = _normalize_value(value)
    fn = getattr(contract.functions, fn_name)(*args)

    tx_params = {
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address, "pending"),
        "chainId": chain_id,
        "value": v_wei,
    }

    # Estimar gas con buena info de error si revierte
    try:
        gas = fn.estimate_gas(tx_params)
    except ContractCustomError as e:
        # revert personalizado del contrato
        raise RuntimeError(f"Revert (custom error) al estimar gas para '{fn_name}': {e}") from e
    except ValueError as e:
        # error genérico RPC (sin fondos, require(false), etc.)
        raise RuntimeError(f"No se pudo estimar gas para '{fn_name}': {e}") from e

    tx_params["gas"] = int(gas * 1.2)

    # EIP-1559 (fallback legacy si la chain no expone baseFeePerGas)
    latest = w3.eth.get_block("latest")
    base_fee = latest.get("baseFeePerGas")
    if base_fee is not None:
        max_priority = w3.to_wei(2, "gwei")
        max_fee = int(base_fee * 2) + max_priority
        tx_params["maxFeePerGas"] = max_fee
        tx_params["maxPriorityFeePerGas"] = max_priority
    else:
        tx_params["gasPrice"] = w3.eth.gas_price

    tx = fn.build_transaction(tx_params)
    signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    return tx_hash.hex()


def get_basic_info():
    w3 = _build_w3()
    net_id = w3.net.version
    latest = w3.eth.block_number
    return {"connected": True, "network_id": net_id, "latest_block": latest}
