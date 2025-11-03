import json
import os
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request
from web3 import Web3

bp = Blueprint("blockchain", __name__)

# ABI (Etherscan + caché en DB)
from app.services.abi_service import (
    get_cached_record,
    get_or_fetch_record,
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


def _checksum(addr: str) -> str:
    return Web3.to_checksum_address(addr)


def _iso(dt) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z" if dt else None


def _as_bool(v) -> bool:
    return str(v).lower() in ("1", "true", "yes", "on")


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
          required:
            - address
            - abi
          properties:
            address: {type: string, example: "0x3245166A4399A34A76cc9254BC13Aae3dA07e27b"}
            network: {type: string, example: "sepolia"}
            abi:
              type: array
              items: {type: object}
            source:
              type: string
              example: "manual"
          example:
            address: "0x3245166A4399A34A76cc9254BC13Aae3dA07e27b"
            network: "sepolia"
            abi: []
            source: "manual"
    responses:
      201: {description: Created}
      200: {description: Updated}
      400: {description: Faltan campos}
      500: {description: Error servidor}
    """
    data = request.get_json(silent=True) or {}
    address = data.get("address")
    network = (data.get("network") or os.getenv("ETHERSCAN_NETWORK", "sepolia")).strip().lower()
    abi = data.get("abi")
    source = data.get("source", "manual")

    # Permitir abi=[] como válido; solo rechazar si es None
    if not address or abi is None:
        return jsonify({"ok": False, "error": "Faltan 'address' o 'abi'"}), 400

    # Acepta abi como lista de dicts o string JSON
    abi_parsed = json.loads(abi) if isinstance(abi, str) else abi
    try:
        prev = get_cached_record(address, network)
        rec = save_abi(address, abi_parsed, network=network, source=source)
        action = "updated" if prev else "created"
        status_code = 200 if prev else 201

        return jsonify({
            "ok": True,
            "action": action,
            "address": _checksum(rec.address),
            "network": rec.network,
            "source": rec.source,
            "abi_len": len(rec.abi) if isinstance(rec.abi, list) else None,
            "created_at": _iso(rec.created_at),
            "updated_at": _iso(rec.updated_at),
        }), status_code

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


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
        example: "0x3245166A4399A34A76cc9254BC13Aae3dA07e27b"
      - in: query
        name: network
        required: false
        type: string
        default: sepolia
        example: "sepolia"
      - in: query
        name: force_refresh
        required: false
        type: boolean
        default: false
        example: false
    responses:
      200: {description: OK}
      400: {description: Faltan campos}
      500: {description: Error servidor}
    """
    address = request.args.get("address")
    network = (request.args.get("network") or os.getenv("ETHERSCAN_NETWORK", "sepolia")).strip().lower()
    force_refresh = _as_bool(request.args.get("force_refresh", "false"))

    if not address:
        return jsonify({"ok": False, "error": "Falta 'address'"}), 400

    try:
        if force_refresh:
            # Forzar obtención fresca desde Etherscan y persistir
            fresh_abi = fetch_abi_from_etherscan(address, network=network)
            rec = save_abi(address, fresh_abi, network=network, source="etherscan")
            src = "etherscan"
        else:
            # Intentar DB; si no hay, fetch + persist
            rec = get_cached_record(address, network)
            if rec:
                src = rec.source or "db"
            else:
                rec = get_or_fetch_record(address, network)
                src = "etherscan"

        return jsonify({
            "ok": True,
            "address": _checksum(rec.address),
            "network": rec.network,
            "source": src,
            "abi": rec.abi,
            "created_at": _iso(rec.created_at),
            "updated_at": _iso(rec.updated_at),
        }), 200

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
          required:
            - contract_address
            - function
          properties:
            contract_address: {type: string, example: "0x3245166A4399A34A76cc9254BC13Aae3dA07e27b"}
            function: {type: string, example: "symbol"}
            args:
              type: array
              items: {type: string}
              example: []
            network: {type: string, example: "sepolia"}
            force_refresh: {type: boolean, example: false}
            abi_path: {type: string}
            abi:
              type: array
              items: {type: object}
            cache_manual: {type: boolean, example: false}
          example:
            contract_address: "0x3245166A4399A34A76cc9254BC13Aae3dA07e27b"
            function: "symbol"
            args: []
            network: "sepolia"
            force_refresh: false
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

    # Flags y red (permitir override por body)
    force_refresh = _as_bool(data.get("force_refresh", False))
    cache_manual = _as_bool(data.get("cache_manual", False))
    network = (data.get("network") or os.getenv("ETHERSCAN_NETWORK", "sepolia")).strip().lower()

    if not func_name:
        return jsonify({"ok": False, "error": "Falta 'function'"}), 400
    if not contract_address:
        return jsonify({"ok": False, "error": "Falta contract_address (o env CONTRACT_ADDRESS)"}), 400

    try:
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
            rec = save_abi(contract_address, fresh, network=network, source="etherscan")
            abi = rec.abi
            resolved_from = "etherscan"

        elif data.get("abi_path") or (abi_path and os.path.exists(abi_path)):
            abi = _load_abi(abi_path)
            resolved_from = "file"
            if cache_manual:
                save_abi(contract_address, abi, network=network, source="manual")

        else:
            rec = get_or_fetch_record(contract_address, network=network)
            abi = rec.abi
            resolved_from = rec.source or "db"

        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=abi
        )

        if not hasattr(contract.functions, func_name):
            return jsonify({"ok": False, "error": f"Función no existe en ABI: {func_name}"}), 400

        fn = getattr(contract.functions, func_name)(*args)
        result = fn.call()

        return jsonify({
            "ok": True,
            "address": Web3.to_checksum_address(contract_address),
            "network": network,
            "function": func_name,
            "args": args,
            "abi_source": resolved_from,
            "result": _to_jsonable(result),
        }), 200

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/send", methods=["POST"])
def send_tx():
    """
    Blockchain: encolar transacción firmada (vía Celery) con overrides dinámicos.
    Permite pasar en el body:
      - contract_address (opcional; si falta usa ENV CONTRACT_ADDRESS)
      - abi (inline)  o  abi_path  o  force_refresh=true (Etherscan)
      - network (p.ej. "sepolia")
      - function, args, value (wei)
    ---
    tags: [Blockchain]
    consumes: [application/json]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [function]
          properties:
            contract_address: {type: string, example: "0x749751AD2D1927b21a643788B5Ed5f568e4d9C6C"}
            network: {type: string, example: "sepolia"}
            abi: {type: array, items: {type: object}}
            abi_path: {type: string, example: "/app/app/abi/ERC20.json.bak"}
            force_refresh: {type: boolean, example: true}
            cache_manual: {type: boolean, example: true}
            function: {type: string, example: "deposit"}
            args: {type: array, items: {}, example: []}
            value: {type: number, example: 1000000000000000}
          example:
            contract_address: "0x749751AD2D1927b21a643788B5Ed5f568e4d9C6C"
            network: "sepolia"
            function: "deposit"
            args: []
            value: 1000000000000000
            force_refresh: true
            cache_manual: false
    responses:
      202: {description: Aceptado}
      400: {description: Faltan/Inválidos}
      501: {description: Task no disponible}
      500: {description: Error servidor}
    """
    data = request.get_json(silent=True) or {}

    func_name = data.get("function") or data.get("fn_name")
    args = data.get("args", [])
    value = data.get("value", 0)

    if not func_name:
        return jsonify({"ok": False, "error": "Falta 'function'"}), 400
    if not isinstance(args, list):
        return jsonify({"ok": False, "error": "'args' debe ser una lista"}), 400
    try:
        # normaliza value (admite "10" o "0x...")
        value = int(value, 0) if isinstance(value, str) else int(value or 0)
    except Exception:
        return jsonify({"ok": False, "error": "'value' debe ser un entero"}), 400

    # Overrides que viajan a la task
    overrides = {
        "contract_address": data.get("contract_address"),
        "network": (data.get("network") or os.getenv("ETHERSCAN_NETWORK", "sepolia")).strip().lower(),
        "abi": data.get("abi"),
        "abi_path": data.get("abi_path"),
        "force_refresh": bool(data.get("force_refresh", False)),
        "cache_manual": bool(data.get("cache_manual", False)),
    }

    try:
        from app.tasks.blockchain_tasks import send_and_wait
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": "Task 'send_and_wait' no está disponible.",
            "detail": str(e),
        }), 501

    try:
        job = AnalysisJob(status="queued", params=data)
        db.session.add(job)
        db.session.commit()

        async_res = send_and_wait.delay(job.id, func_name, args, value, overrides)
        job.task_id = async_res.id
        db.session.commit()

        return jsonify({"ok": True, "job_id": job.id, "task_id": async_res.id, "status": "queued"}), 202

    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": "No se pudo encolar la tarea", "detail": str(e)}), 500


@bp.route("/procesar", methods=["POST"])
def procesar_alias():
    """
    Alias de /send con mismo comportamiento dinámico.
    Si recibe {"text": "..."} sin "function", lo mapea a {"function":"echo","args":[text]}.
    ---
    tags: [Blockchain]
    """
    payload = request.get_json(silent=True) or {}
    if "text" in payload and "function" not in payload:
        payload = {"function": "echo", "args": [payload["text"]]}

    # Reutiliza la lógica de /send
    request._cached_json = (payload, payload)  # pequeño truco para reutilizar
    return send_tx()
