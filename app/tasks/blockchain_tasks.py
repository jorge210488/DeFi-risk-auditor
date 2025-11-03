# app/tasks/blockchain_tasks.py
from datetime import datetime
from typing import Any, Dict, Optional
from celery import shared_task
from hexbytes import HexBytes

from app.models import db, AnalysisJob
from app.services.blockchain_service import send_function, _build_w3


def _to_hex(x):
    return x.hex() if isinstance(x, (bytes, HexBytes)) else x


def _clean_receipt(receipt: Optional[dict]) -> Optional[dict]:
    if not receipt:
        return None
    cleaned = {
        "transactionHash": _to_hex(receipt.get("transactionHash")),
        "blockHash": _to_hex(receipt.get("blockHash")),
        "blockNumber": receipt.get("blockNumber"),
        "transactionIndex": receipt.get("transactionIndex"),
        "cumulativeGasUsed": receipt.get("cumulativeGasUsed"),
        "effectiveGasPrice": receipt.get("effectiveGasPrice"),
        "gasUsed": receipt.get("gasUsed"),
        "status": receipt.get("status"),
        "contractAddress": receipt.get("contractAddress"),
    }
    return {k: v for k, v in cleaned.items() if v is not None}


@shared_task(name="blockchain.send_and_wait")
def send_and_wait(job_id: int, fn_name: str, args: list, value: int = 0, overrides: Optional[Dict[str, Any]] = None):
    """
    Firma/manda la tx con 'send_function' usando overrides (contrato/ABI/red),
    guarda el tx_hash, espera receipt y actualiza el AnalysisJob.
    """
    job = db.session.get(AnalysisJob, job_id)
    if not job:
        return {"error": f"AnalysisJob id {job_id} not found"}

    try:
        tx_hash = send_function(fn_name, *args, value=value, overrides=overrides or {})
        job.status = "pending"
        job.result = {"tx_hash": tx_hash}
        job.updated_at = datetime.utcnow()
        db.session.commit()

        w3 = _build_w3()
        receipt_obj = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=600)
        receipt_dict = dict(receipt_obj)

        job.status = "done"
        job.result = {"tx_hash": tx_hash, "receipt": _clean_receipt(receipt_dict)}
        job.updated_at = datetime.utcnow()
        db.session.commit()

        return {"tx_hash": tx_hash, "status": "mined"}

    except Exception as e:
        job.status = "error"
        job.result = {"error": str(e)}
        job.updated_at = datetime.utcnow()
        db.session.commit()
        raise
