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
    """Carga un archivo de ABI desde disco y lo devuelve como JSON (lista/dict)."""
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
    """
    Blockchain: ping
    ---
    tags: [Blockchain]
    responses:
      200: {description: OK}
    """
    return jsonify({"ok": True}), 200


@bp.route("/health", methods=["GET"])
def health():
    """
    Blockchain: health
    ---
    tags: [Blockchain]
    responses:
      200: {description: OK}
    """
    return jsonify({"ok": True}), 200


@bp.route("/info", methods=["GET"])
def info():
    """
    Blockchain: info de red
    ---
    tags: [Blockchain]
    responses:
      200: {description: OK}
      503: {description: Error de conexión}
    """
    try:
        w3 = _make_w3()
        chain_id = w3.eth.chain_id
        latest = w3.eth.get_block("latest").number
        return jsonify({"ok": True, "chain_id": chain_id, "latest_block": latest}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 503


@bp.route("/abi", methods=["POST"])
def abi_save():
    """
    Blockchain: guardar ABI manualmente en DB
    ---
    tags: [Blockchain]
    consumes: [application/json]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            address: {type: string, example: "0x..."}
            network: {type: string, example: "sepolia"}
            abi:
              type: array
              items: {type: object}
            source:
              type: string
              example: "manual"
    responses:
      200: {description: OK}
      400: {description: Faltan campos}
    """
    data = request.get_json(silent=True) or {}
    address = data.get("address")
    network = data.get("network", os.getenv("ETHERSCAN_NETWORK", "sepolia"))
    abi = data.get("abi")
    source = data.get("source", "manual")

    # Mejora: permitir abi=[] como válido; solo rechazar si es None
    if not address or abi is None:
        return jsonify({"ok": False, "error": "Faltan 'address' o 'abi'"}), 400

    # Acepta abi como lista de dicts o string JSON
    abi_parsed = json.loads(abi) if isinstance(abi, str) else abi
    try:
        save_abi(address, abi_parsed, network=network, source=source)
    except Exception as e:
        # Mejora: devolver error controlado en JSON si falla la persistencia
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True}), 200


@bp.route("/abi", methods=["GET"])
def abi_resolve():
    """
    Blockchain: obtener ABI resuelto (DB/Etherscan)
    ---
    tags: [Blockchain]
    parameters:
      - in: query
        name: address
        required: true
        type: string
      - in: query
        name: network
        required: false
        type: string
        default: sepolia
      - in: query
        name: force_refresh
        required: false
        type: boolean
        default: false
    responses:
      200: {description: OK}
      400: {description: Faltan campos}
      500: {description: Error servidor}
    """
    address = request.args.get("address")
    network = request.args.get("network", os.getenv("ETHERSCAN_NETWORK", "sepolia"))
    force_refresh = request.args.get("force_refresh", "false").lower() in ("1", "true", "yes")

    if not address:
        return jsonify({"ok": False, "error": "Falta 'address'"}), 400

    try:
        if force_refresh:
            # Forzar obtención fresca desde Etherscan
            fresh_abi = fetch_abi_from_etherscan(address, network=network)
            save_abi(address, fresh_abi, network=network, source="etherscan")
            abi = fresh_abi
            src = "etherscan"
        else:
            # Obtener de DB o Etherscan (caché)
            abi = get_abi_for_address(address, network=network)
            src = "db_or_etherscan"

        return jsonify({"ok": True, "source": src, "abi": abi}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/call", methods=["POST"])
def call_contract():
    """
    Blockchain: llamada de solo lectura a contrato
    ---
    tags: [Blockchain]
    consumes: [application/json]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            contract_address: {type: string, example: "0x..."}
            function: {type: string, example: "symbol"}
            args:
              type: array
              items: {type: string}
            force_refresh: {type: boolean, example: false}
            abi_path: {type: string}
            abi:
              type: array
              items: {type: object}
            cache_manual: {type: boolean}
    responses:
      200: {description: OK}
      400: {description: Error del cliente}
      500: {description: Error servidor}
    """
    data = request.get_json(silent=True) or {}

    # Compat: soporta "function" y "fn_name"
    func_name = data.get("function") or data.get("fn_name")
    args = data.get("args", [])

    contract_address = data.get("contract_address") or os.getenv("CONTRACT_ADDRESS")
    abi_path = data.get("abi_path") or os.getenv("CONTRACT_ABI_PATH", "/app/app/abi/Contract.json")
    abi_inline = data.get("abi")
    # Mantener comportamiento original (bool() sobre el valor recibido)
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
    Blockchain: encolar transacción firmada (vía Celery)
    ---
    tags: [Blockchain]
    consumes: [application/json]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            function: {type: string, example: "transfer"}
            args:
              type: array
              items: {}
            value: {type: number, example: 0}
    responses:
      202: {description: Aceptado}
      400: {description: Faltan campos}
      501: {description: Task no disponible}
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
