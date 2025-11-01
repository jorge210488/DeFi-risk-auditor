# app/tasks/blockchain_tasks.py

from datetime import datetime
from celery import shared_task
from hexbytes import HexBytes

from app.models import db, AnalysisJob
from app.services.blockchain_service import send_function, _build_w3

def _clean_receipt(receipt: dict) -> dict:
    """
    Convert the web3 transaction receipt (with HexBytes/AttributeDict) into a JSON-serializable dict.
    It includes important fields and normalizes any byte values to hex strings.
    """
    if receipt is None:
        return None

    def _to_hex(x):
        # Convert HexBytes or bytes to hex string, leave other types as-is
        return x.hex() if isinstance(x, (bytes, HexBytes)) else x

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
        # Note: logs and logsBloom are omitted for brevity; include them if needed:
        # "logsBloom": _to_hex(receipt.get("logsBloom")),
        # "logs": [
        #     {
        #         "address": log.get("address"),
        #         "data": log.get("data"),
        #         "topics": [_to_hex(t) for t in log.get("topics", [])],
        #         "logIndex": log.get("logIndex"),
        #         "transactionIndex": log.get("transactionIndex"),
        #         "transactionHash": _to_hex(log.get("transactionHash")),
        #         "blockHash": _to_hex(log.get("blockHash")),
        #         "blockNumber": log.get("blockNumber"),
        #     } for log in receipt.get("logs", [])
        # ],
    }
    # Remove any keys with value None to clean up the result
    return {k: v for k, v in cleaned.items() if v is not None}

@shared_task(name="blockchain.send_and_wait")
def send_and_wait(job_id: int, fn_name: str, args: list, value: int = 0):
    """
    Celery task to send a blockchain transaction and wait for its receipt.
    - Signs and sends the transaction using send_function.
    - Updates the AnalysisJob status to 'pending' with the transaction hash.
    - Waits for the transaction receipt and then updates the job status to 'done' with the receipt.
    - If any step fails, marks the job as 'error' and stores the error.
    """
    job = db.session.get(AnalysisJob, job_id)
    if not job:
        return {"error": f"AnalysisJob id {job_id} not found"}

    try:
        # 1) Sign and send the transaction
        tx_hash = send_function(fn_name, *args, value=value)
        # Update job to pending state with the transaction hash
        job.status = "pending"
        job.result = {"tx_hash": tx_hash}
        job.updated_at = datetime.utcnow()
        db.session.commit()

        # 2) Wait for the transaction to be mined (up to 600 seconds)
        w3 = _build_w3()
        receipt_obj = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=600)
        receipt_dict = dict(receipt_obj)  # Convert AttributeDict to dict for processing
        # Clean the receipt for JSON serialization and store it
        job.status = "done"
        job.result = {"tx_hash": tx_hash, "receipt": _clean_receipt(receipt_dict)}
        job.updated_at = datetime.utcnow()
        db.session.commit()

        # Return a concise result (the full receipt is stored in the job result)
        return {"tx_hash": tx_hash, "status": "mined"}

    except Exception as e:
        # If any error occurs (transaction failed, timeout, etc.), mark job as error
        job.status = "error"
        job.result = {"error": str(e)}
        job.updated_at = datetime.utcnow()
        db.session.commit()
        # Re-raise the exception to let Celery record the failure (for monitoring/retry if needed)
        raise
