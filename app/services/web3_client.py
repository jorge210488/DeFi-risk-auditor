# app/services/web3_client.py
import os
from functools import lru_cache
from web3 import Web3

# v6: importar el middleware así
from web3.middleware import geth_poa_middleware


def _make_w3() -> Web3:
    uri = os.getenv("WEB3_PROVIDER_URI")
    if not uri:
        raise RuntimeError("WEB3_PROVIDER_URI no está definido")

    # Timeout de 10s en requests HTTP
    w3 = Web3(Web3.HTTPProvider(uri, request_kwargs={"timeout": 10}))

    # POA (Sepolia, etc.) si viene habilitado
    use_poa = os.getenv("WEB3_USE_POA", "false").lower() == "true"
    if use_poa:
        # En v6 se inyecta así:
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)

    if not w3.is_connected():
        raise RuntimeError("No se pudo conectar al nodo Web3")

    return w3


@lru_cache(maxsize=1)
def get_w3() -> Web3:
    """Singleton perezoso: se crea la primera vez y se reusa."""
    return _make_w3()
