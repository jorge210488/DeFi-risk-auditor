# app/routes/blockchain_routes.py
import json
import os
from pathlib import Path
from flask import Blueprint, jsonify, request

bp = Blueprint("blockchain", __name__)

# --- Helpers locales ---

def _load_abi(abi_path: str):
    p = Path(abi_path)
    if not p.exists():
        raise FileNotFoundError(f"ABI no encontrado: {abi_path}")
    return json.loads(p.read_text(encoding="utf-8"))


def _make_w3():
    """
    Crea una instancia Web3 simple para llamadas de solo lectura.
    Para envíos de TX usa mejor la task de Celery (blockchain_tasks).
    """
    try:
        from web3 import Web3
        try:
            from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware
            poa_mw = ExtraDataToPOAMiddleware
        except Exception:
            poa_mw = None

        provider_uri = os.getenv("WEB3_PROVIDER_URI")
        if not provider_uri:
            raise RuntimeError("WEB3_PROVIDER_URI no configurado")

        # 👇 CAMBIO CLAVE: usa timeout explícito
        w3 = Web3(Web3.HTTPProvider(provider_uri, request_kwargs={"timeout": 10}))

        if os.getenv("WEB3_USE_POA", "false").lower() in ("1", "true", "yes"):
            if poa_mw:
                w3.middleware_onion.inject(poa_mw, layer=0)

        if not w3.is_connected():
            raise RuntimeError("No se pudo conectar al nodo Web3")

        return w3
    except Exception as e:
        raise RuntimeError(f"Error inicializando Web3: {e}") from e


# --- Rutas ---

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
    data = request.get_json(silent=True) or {}
    func_name = data.get("function")
    args = data.get("args", [])

    contract_address = data.get("contract_address") or os.getenv("CONTRACT_ADDRESS")
    abi_path = data.get("abi_path") or os.getenv("CONTRACT_ABI_PATH", "/app/app/abi/Contract.json")

    if not func_name:
        return jsonify({"ok": False, "error": "Falta 'function'"}), 400
    if not contract_address:
        return jsonify({"ok": False, "error": "Falta contract_address (o env CONTRACT_ADDRESS)"}), 400

    try:
        w3 = _make_w3()
        abi = _load_abi(abi_path)
        contract = w3.eth.contract(address=w3.to_checksum_address(contract_address), abi=abi)
        if not hasattr(contract.functions, func_name):
            return jsonify({"ok": False, "error": f"Función no existe en ABI: {func_name}"}), 400

        fn = getattr(contract.functions, func_name)(*args)
        result = fn.call()
        return jsonify({"ok": True, "result": result}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/send", methods=["POST"])
def send_tx():
    data = request.get_json(silent=True) or {}

    try:
        from app.tasks.blockchain_tasks import send_and_wait
    except Exception:
        return jsonify({
            "ok": False,
            "error": "Task 'send_and_wait' no está disponible. Crea app/tasks/blockchain_tasks.py."
        }), 501

    async_res = send_and_wait.delay(data)
    return jsonify({"ok": True, "task_id": async_res.id}), 202
