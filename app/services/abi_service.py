import os
import json
import requests
from datetime import datetime
from typing import Optional, List, Union
from web3 import Web3

from app.models import db
from app.models.contract_abi import ContractABI

# URL base de la API Etherscan v2 (se puede sobrescribir con variable de entorno)
ETHERSCAN_V2_BASE = os.getenv("ETHERSCAN_V2_BASE", "https://api.etherscan.io/v2/api")


def _norm_addr(addr: str) -> str:
    """Normaliza una dirección Ethereum y la convierte a formato checksum."""
    if not addr:
        raise ValueError("Dirección de contrato vacía o inválida")
    # Convierte a checksum (puede lanzar ValueError si la dirección no es válida)
    return Web3.to_checksum_address(addr)


def _norm_net(net: Optional[str]) -> str:
    """Normaliza el nombre de la red (por defecto 'sepolia')."""
    return (net or "sepolia").strip().lower()


def get_cached_abi(address: str, network: str = "sepolia") -> Optional[List[dict]]:
    """Busca en la base de datos la ABI caché de un contrato dado (address, network)."""
    ca = _norm_addr(address)
    nw = _norm_net(network)
    record = ContractABI.query.filter_by(address=ca.lower(), network=nw).first()
    return record.abi if record else None


def save_abi(address: str, abi: Union[str, List[dict]], network: str = "sepolia", source: str = "manual") -> None:
    """Guarda una ABI en la base de datos, insertando o actualizando según corresponda."""
    # Acepta ABI como lista de dict o como cadena JSON y la normaliza a lista
    if isinstance(abi, str):
        abi = json.loads(abi)
    if not isinstance(abi, list):
        raise RuntimeError("Formato de ABI inválido: se esperaba una lista JSON")

    ca = _norm_addr(address)    # Normaliza a checksum
    nw = _norm_net(network)
    now = datetime.utcnow()

    # Busca si ya existe un registro para esa dirección+red
    rec = ContractABI.query.filter_by(address=ca.lower(), network=nw).first()
    if rec:
        # Si existe, actualiza la ABI, la fuente y la fecha de actualización
        rec.abi = abi
        rec.source = source
        rec.updated_at = now
    else:
        # Si no existe, crea un nuevo registro con created_at y updated_at
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


def _parse_v2_result(data: dict) -> List[dict]:
    """
    Parsea la respuesta de Etherscan v2 para extraer la ABI.
    Etherscan v2 puede devolver la ABI en diferentes estructuras:
      - data["result"]["contractInfo"][0]["ABI"] (o "ContractInfo")
      - data["result"][0]["ABI"]
      - data["result"] como cadena JSON (caso fallback)
    """
    res = data.get("result")
    if not res:
        raise RuntimeError(f"Etherscan v2: respuesta sin 'result': {data}")

    # Caso 1: resultado es un dict con clave contractInfo/ContractInfo que contiene lista
    if isinstance(res, dict):
        info_list = res.get("contractInfo") or res.get("ContractInfo")
        if isinstance(info_list, list) and info_list:
            abi_str = info_list[0].get("ABI") or info_list[0].get("Abi") or info_list[0].get("abi")
            if not abi_str:
                raise RuntimeError("Etherscan v2: campo ABI vacío en la respuesta")
            abi = json.loads(abi_str)
            if not isinstance(abi, list):
                raise RuntimeError("Etherscan v2: ABI obtenido no es una lista")
            return abi

    # Caso 2: resultado es una lista de dicts con clave ABI/Abi/abi
    if isinstance(res, list) and res and isinstance(res[0], dict) and any(k in res[0] for k in ("ABI", "Abi", "abi")):
        abi_str = res[0].get("ABI") or res[0].get("Abi") or res[0].get("abi")
        abi = json.loads(abi_str)
        if not isinstance(abi, list):
            raise RuntimeError("Etherscan v2: ABI obtenido no es una lista")
        return abi

    # Caso 3: resultado es un string (posiblemente JSON)
    if isinstance(res, str):
        try:
            abi = json.loads(res)
            if isinstance(abi, list):
                return abi
        except json.JSONDecodeError:
            pass  # Si no pudo decodificar, manejará el error más abajo

    # Si llegó aquí, no pudo parsear la estructura
    # Si Etherscan devolvió status=0 con mensaje de error, lanzarlo como excepción
    message = data.get("message") or data.get("Message")
    if str(data.get("status")) == "0" and message:
        raise RuntimeError(f"Etherscan error: {message} — {res}")

    raise RuntimeError(f"No se pudo interpretar la respuesta de Etherscan v2: {data}")


def fetch_abi_from_etherscan(address: str, network: str = "sepolia") -> List[dict]:
    """Consulta la API de Etherscan v2 para obtener la ABI de un contrato (requiere ETHERSCAN_API_KEY)."""
    api_key = os.getenv("ETHERSCAN_API_KEY")
    if not api_key:
        raise RuntimeError("ETHERSCAN_API_KEY no está definida en las variables de entorno")

    nw = _norm_net(network)
    # Determina el chain ID: usa ETHERSCAN_CHAIN_ID o WEB3_CHAIN_ID si están, sino infiere por la red
    chainid = os.getenv("ETHERSCAN_CHAIN_ID") or os.getenv("WEB3_CHAIN_ID")
    if not chainid:
        chainid = "11155111" if nw == "sepolia" else "1"  # Sepolia=11155111, Mainnet=1, etc.

    # Parámetros de consulta para Etherscan API v2
    params = {
        "module": "contract",
        "action": "getabi",
        "address": _norm_addr(address),
        "apikey": api_key,
        "chainid": chainid,
    }

    # Realiza la petición GET a Etherscan
    response = requests.get(ETHERSCAN_V2_BASE, params=params, timeout=20)
    response.raise_for_status()
    data = response.json()

    # Si Etherscan indica status 0, considera eso un error con mensaje
    if str(data.get("status")) == "0":
        raise RuntimeError(f"Etherscan error: {data.get('message')} — {data.get('result')}")

    # Parsea y devuelve la ABI como lista de diccionarios
    return _parse_v2_result(data)


def get_or_fetch_abi(address: str, network: str = "sepolia") -> List[dict]:
    """
    Obtiene la ABI de un contrato, usando la base de datos como caché.
    Si no está en la DB, la busca en Etherscan y la almacena.
    """
    nw = _norm_net(network)
    cached = get_cached_abi(address, nw)
    if cached:
        return cached
    fresh_abi = fetch_abi_from_etherscan(address, nw)
    save_abi(address, fresh_abi, network=nw, source="etherscan")
    return fresh_abi

# Alias para uso en rutas
get_abi_for_address = get_or_fetch_abi
