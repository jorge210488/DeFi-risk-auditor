# app/tasks/blockchain_tasks.py
from datetime import datetime
from celery import shared_task
from hexbytes import HexBytes

from app.models import db, AnalysisJob
from app.services.blockchain_service import send_function, _build_w3


def _clean_receipt(r):
    """
    Convierte el receipt de web3 (con HexBytes/AttributeDict) a un dict JSON-serializable.
    Incluye campos útiles y normaliza hashes a hex().
    """
    if r is None:
        return None

    def _hx(x):
        return x.hex() if isinstance(x, (bytes, HexBytes)) else x

    out = {
        "transactionHash": _hx(r.get("transactionHash")),
        "blockHash": _hx(r.get("blockHash")),
        "blockNumber": r.get("blockNumber"),
        "transactionIndex": r.get("transactionIndex"),
        "cumulativeGasUsed": r.get("cumulativeGasUsed"),
        "effectiveGasPrice": r.get("effectiveGasPrice"),
        "gasUsed": r.get("gasUsed"),
        "status": r.get("status"),
        "contractAddress": r.get("contractAddress"),
        # logs y logsBloom pueden ser grandes; si los quieres, activa esto:
        # "logsBloom": _hx(r.get("logsBloom")),
        # "logs": [
        #     {
        #         "address": log.get("address"),
        #         "data": log.get("data"),
        #         "topics": [_hx(t) for t in log.get("topics", [])],
        #         "logIndex": log.get("logIndex"),
        #         "transactionIndex": log.get("transactionIndex"),
        #         "transactionHash": _hx(log.get("transactionHash")),
        #         "blockHash": _hx(log.get("blockHash")),
        #         "blockNumber": log.get("blockNumber"),
        #     } for log in r.get("logs", [])
        # ],
    }
    return {k: v for k, v in out.items() if v is not None}


@shared_task(name="blockchain.send_and_wait")
def send_and_wait(job_id: int, fn_name: str, args: list, value: int = 0):
    """
    - Firma y envía la TX (send_function)
    - Actualiza el AnalysisJob a 'pending' con tx_hash
    - Espera el receipt y marca 'done'
    """
    job = AnalysisJob.query.get(job_id)
    if not job:
        # No hay job en BD: devolvemos algo informativo (no explota el worker)
        return {"error": "job no encontrado", "job_id": job_id}

    try:
        # 1) Enviar TX
        tx_hash = send_function(fn_name, *args, value=value)

        job.status = "pending"
        job.result = {"tx_hash": tx_hash}
        job.updated_at = datetime.utcnow()
        db.session.commit()

        # 2) Esperar receipt sin bloquear la request original (esto corre en worker)
        w3 = _build_w3()
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=600)

        job.status = "done"
        job.result = {"tx_hash": tx_hash, "receipt": _clean_receipt(dict(receipt))}
        job.updated_at = datetime.utcnow()
        db.session.commit()

        return {"tx_hash": tx_hash, "status": "mined"}

    except Exception as e:
        job.status = "error"
        job.result = {"error": str(e)}
        job.updated_at = datetime.utcnow()
        db.session.commit()
        # Re-raise para que Celery registre el failure
        raise
