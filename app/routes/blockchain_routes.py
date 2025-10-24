# app/routes/blockchain_routes.py
import json
import os
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request

bp = Blueprint("blockchain", __name__)

# ABI auto (Etherscan + caché en DB)
from app.services.abi_service import (
    get_abi_for_address,
    fetch_abi_from_etherscan,
    save_abi,
)
from app.models import db, AnalysisJob


# --- Helpers locales ---

def _load_abi(abi_path: str):
    p = Path(abi_path)
    if not p.exists():
        raise FileNotFoundError(f"ABI no encontrado: {abi_path}")
    return json.loads(p.read_text(encoding="utf-8"))


def _make_w3():
    """
    Crea una instancia Web3 simple para llamadas de solo lectura.
    Para envíos de TX usa la task de Celery (blockchain_tasks).
    """
    try:
        from web3 import Web3
        try:
            # PoA (Sepolia/Goerli/etc). Web3 v6
            from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware
            poa_mw = ExtraDataToPOAMiddleware
        except Exception:
            poa_mw = None

        provider_uri = os.getenv("WEB3_PROVIDER_URI")
        if not provider_uri:
            raise RuntimeError("WEB3_PROVIDER_URI no configurado")

        # timeout explícito
        w3 = Web3(Web3.HTTPProvider(provider_uri, request_kwargs={"timeout": 10}))

        if os.getenv("WEB3_USE_POA", "false").lower() in ("1", "true", "yes"):
            if poa_mw:
                w3.middleware_onion.inject(poa_mw, layer=0)

        if not w3.is_connected():
            raise RuntimeError("No se pudo conectar al nodo Web3")

        return w3
    except Exception as e:
        raise RuntimeError(f"Error inicializando Web3: {e}") from e


def _to_jsonable(x: Any):
    """Normaliza a JSON (HexBytes, bytes, tuplas, listas, dicts)."""
    try:
        from hexbytes import HexBytes
    except Exception:
        HexBytes = bytes  # fallback

    if isinstance(x, (bytes, HexBytes)):
        return x.hex()
    if isinstance(x, (list, tuple)):
        return [_to_jsonable(i) for i in x]
    if isinstance(x, dict):
        return {k: _to_jsonable(v) for k, v in x.items()}
    return x


# --- Rutas ---

@bp.route("/ping", methods=["GET"])
def ping():
    return jsonify({"ok": True}), 200


@bp.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True}), 200


@bp.route("/info", methods=["GET"])
def info():
    try:
        w3 = _make_w3()
        chain_id = w3.eth.chain_id
        latest = w3.eth.get_block("latest").number
        return jsonify({"ok": True, "chain_id": chain_id, "latest_block": latest}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 503


@bp.route("/call", methods=["POST"])
def call_contract():
    """
    Prioridad de ABI (respetando force_refresh):
      1) 'abi' inline (lista/dict o string JSON)  [opcional: cache_manual:true -> guarda en DB]
      2) force_refresh==true  -> bajar desde Etherscan (V2) y cachear
      3) 'abi_path' (o env CONTRACT_ABI_PATH si existe)  [opcional: cache_manual:true -> guarda en DB]
      4) cache Etherscan (get_abi_for_address: DB o fetch)

    Body ejemplo:
    {
      "function": "symbol",          // o "fn_name"
      "args": [],
      "contract_address": "0x...",
      "abi_path": "/app/app/abi/ERC20.json",
      "abi": [...],                  // opcional
      "force_refresh": false,        // si true, vuelve a bajar de Etherscan
      "cache_manual": true           // si usas abi inline o archivo, guarda en DB
    }
    """
    data = request.get_json(silent=True) or {}

    # Compat: soporta "function" y "fn_name"
    func_name = data.get("function") or data.get("fn_name")
    args = data.get("args", [])

    contract_address = data.get("contract_address") or os.getenv("CONTRACT_ADDRESS")
    abi_path = data.get("abi_path") or os.getenv("CONTRACT_ABI_PATH", "/app/app/abi/Contract.json")
    abi_inline = data.get("abi")
    force_refresh = bool(data.get("force_refresh"))
    cache_manual = bool(data.get("cache_manual"))
    network = os.getenv("ETHERSCAN_NETWORK", "sepolia")

    if not func_name:
        return jsonify({"ok": False, "error": "Falta 'function'"}), 400
    if not contract_address:
        return jsonify({"ok": False, "error": "Falta contract_address (o env CONTRACT_ADDRESS)"}), 400

    try:
        from web3 import Web3
        w3 = _make_w3()

        # --- Resolver ABI (orden con force_refresh) ---
        resolved_from = None

        if abi_inline:
            abi = json.loads(abi_inline) if isinstance(abi_inline, str) else abi_inline
            resolved_from = "inline"
            if cache_manual:
                save_abi(contract_address, abi, network=network, source="manual")

        elif force_refresh:
            fresh = fetch_abi_from_etherscan(contract_address, network=network)
            save_abi(contract_address, fresh, network=network, source="etherscan")
            abi = fresh
            resolved_from = "etherscan"

        elif data.get("abi_path") or (abi_path and os.path.exists(abi_path)):
            abi = _load_abi(abi_path)
            resolved_from = "file"
            if cache_manual:
                save_abi(contract_address, abi, network=network, source="manual")

        else:
            abi = get_abi_for_address(contract_address, network=network)
            if isinstance(abi, str):
                abi = json.loads(abi)
            resolved_from = "db_or_etherscan"

        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=abi
        )

        if not hasattr(contract.functions, func_name):
            return jsonify({"ok": False, "error": f"Función no existe en ABI: {func_name}"}), 400

        fn = getattr(contract.functions, func_name)(*args)
        result = fn.call()
        return jsonify({"ok": True, "source": resolved_from, "result": _to_jsonable(result)}), 200

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/send", methods=["POST"])
def send_tx():
    """
    Encola una transacción firmada vía Celery y guarda el AnalysisJob.
    Body JSON:
      {
        "function": "transfer",   // o "fn_name"
        "args": ["0xDEST", 1000],
        "value": 0
      }
    """
    data = request.get_json(silent=True) or {}

    func_name = data.get("function") or data.get("fn_name")
    args = data.get("args", [])
    value = data.get("value", 0)

    if not func_name:
        return jsonify({"ok": False, "error": "Falta 'function'"}), 400

    # Import diferido de la task
    try:
        from app.tasks.blockchain_tasks import send_and_wait
    except Exception:
        return jsonify({
            "ok": False,
            "error": "Task 'send_and_wait' no está disponible. Crea app/tasks/blockchain_tasks.py."
        }), 501

    # Crear job y encolar
    job = AnalysisJob(status="queued", params=data)
    db.session.add(job)
    db.session.commit()

    async_res = send_and_wait.delay(job.id, func_name, args, value)
    job.task_id = async_res.id
    db.session.commit()

    return jsonify({"ok": True, "job_id": job.id, "task_id": async_res.id, "status": "queued"}), 202
