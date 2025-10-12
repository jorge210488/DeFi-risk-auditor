# app/services/blockchain_service.py
import json, os
from pathlib import Path
from web3 import Web3
from web3.middleware.geth_poa import geth_poa_middleware

def _build_w3() -> Web3:
    provider = os.getenv("WEB3_PROVIDER_URI")
    if not provider:
        raise RuntimeError("WEB3_PROVIDER_URI no configurado")
    w3 = Web3(Web3.HTTPProvider(provider))
    use_poa = os.getenv("WEB3_USE_POA", "false").lower() == "true"
    if use_poa:
        # para redes tipo PoA
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    if not w3.is_connected():
        raise RuntimeError("No se pudo conectar a la RPC")
    return w3

def _load_contract(w3: Web3):
    addr = os.getenv("CONTRACT_ADDRESS")
    abi_path = os.getenv("CONTRACT_ABI_PATH", "/app/app/abi/Contract.json")
    if not addr:
        raise RuntimeError("CONTRACT_ADDRESS no configurado")
    data = Path(abi_path).read_text(encoding="utf-8")
    abi = json.loads(data)
    return w3.eth.contract(address=Web3.to_checksum_address(addr), abi=abi)

def call_function(fn_name: str, *args, value: int = 0):
    """Lectura (view/pure) — no gasta gas."""
    w3 = _build_w3()
    contract = _load_contract(w3)
    fn = getattr(contract.functions, fn_name)(*args)
    return fn.call({"value": value})

def send_function(fn_name: str, *args, value: int = 0):
    """Escritura — firma y envía transacción. Devuelve tx_hash (hex)."""
    w3 = _build_w3()
    contract = _load_contract(w3)
    private_key = os.getenv("PRIVATE_KEY")
    if not private_key:
        raise RuntimeError("PRIVATE_KEY no configurada")
    account = w3.eth.account.from_key(private_key)
    chain_id = int(os.getenv("WEB3_CHAIN_ID", "1"))

    fn = getattr(contract.functions, fn_name)(*args)

    # Estimación de gas
    gas = fn.estimate_gas({"from": account.address, "value": value})
    # EIP-1559 fees (ajusta a tu red)
    base_fee = w3.eth.get_block("latest")["baseFeePerGas"]
    max_priority = w3.to_wei("2", "gwei")
    max_fee = int(base_fee * 2) + max_priority

    tx = fn.build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "chainId": chain_id,
        "gas": int(gas * 1.2),
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": max_priority,
        "value": value or 0,
    })

    signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    return tx_hash.hex()

def get_basic_info():
    w3 = _build_w3()
    net_id = w3.net.version
    latest = w3.eth.block_number
    return {"connected": True, "network_id": net_id, "latest_block": latest}
