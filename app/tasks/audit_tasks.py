# app/tasks/audit_tasks.py
from datetime import datetime
from typing import Dict, Any
import os

from celery import shared_task
from web3 import Web3

# PoA: intento v6 (ExtraDataToPOAMiddleware) y fallback a geth_poa_middleware
def _poa_middleware():
    try:
        from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware as poa_mw
        return poa_mw
    except Exception:
        try:
            from web3.middleware.geth_poa import geth_poa_middleware as poa_mw
            return poa_mw
        except Exception:
            return None

from app.models import db, AnalysisJob
from app.models.audit import ContractAudit
from app.services.abi_service import get_abi_for_address, fetch_abi_from_etherscan, save_abi
from app.services.ai_service import risk_score


def _make_w3():
    uri = os.getenv("WEB3_PROVIDER_URI")
    if not uri:
        raise RuntimeError("WEB3_PROVIDER_URI no configurado")
    w3 = Web3(Web3.HTTPProvider(uri, request_kwargs={"timeout": 10}))

    if os.getenv("WEB3_USE_POA", "false").lower() in ("1", "true", "yes"):
        poa_mw = _poa_middleware()
        if poa_mw:
            w3.middleware_onion.inject(poa_mw, layer=0)

    if not w3.is_connected():
        raise RuntimeError("No se pudo conectar al nodo Web3")
    return w3


def _safe_call(contract, fn_name: str, *args):
    try:
        if hasattr(contract.functions, fn_name):
            fn = getattr(contract.functions, fn_name)(*args)
            return True, fn.call()
        return False, f"no_fn:{fn_name}"
    except Exception as e:
        return False, str(e)


def _extract_features(w3, address: str, abi: list) -> Dict[str, Any]:
    c = w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)

    fn_names, write_fns, view_fns = [], [], []
    for it in abi:
        if it.get("type") == "function":
            name = it.get("name")
            fn_names.append(name)
            mut = it.get("stateMutability", "")
            if mut in ("view", "pure"):
                view_fns.append(name)
            else:
                write_fns.append(name)

    flags = {
        "has_approve": "approve" in fn_names,
        "has_transferFrom": "transferFrom" in fn_names,
        "has_mint": "mint" in fn_names or "mintTo" in fn_names,
        "has_burn": "burn" in fn_names,
        "has_pause": "pause" in fn_names or "paused" in fn_names,
        "has_owner": "owner" in fn_names or "getOwner" in fn_names,
        "has_transferOwnership": "transferOwnership" in fn_names,
        "has_withdraw": "withdraw" in fn_names,
    }

    code_len = len(w3.eth.get_code(Web3.to_checksum_address(address)))
    is_contract = code_len > 0

    meta = {}
    for key in ("name", "symbol", "decimals", "totalSupply"):
        ok, val = _safe_call(c, key)
        if ok:
            meta[key] = val

    total = len(fn_names) or 1
    write_ratio = len(write_fns) / total
    risky_flags = sum(1 for v in flags.values() if v)

    features = {
        "total_functions": len(fn_names),
        "write_functions": len(write_fns),
        "view_functions": len(view_fns),
        "write_ratio": write_ratio,
        "risky_flags": risky_flags,
        "is_contract": is_contract,
        "code_len": code_len,
        **flags,
        **({k: meta[k] for k in meta}),
    }
    return features


def _level_from_score(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


@shared_task(name="audit.run")
def run_audit(job_id: int, address: str, network: str = "sepolia", force_refresh: bool = False):
    job = AnalysisJob.query.get(job_id)
    if not job:
        return {"error": "job no encontrado", "job_id": job_id}

    audit = ContractAudit(
        address=address.lower(),
        network=network,
        status="running",
        started_at=datetime.utcnow(),
    )
    db.session.add(audit)
    db.session.commit()

    try:
        w3 = _make_w3()

        # Obtener ABI (usa cache a menos que force_refresh sea True)
        if _as_bool(force_refresh):
            fresh = fetch_abi_from_etherscan(address, network=network)
            save_abi(address, fresh, network=network, source="etherscan")
            abi = fresh
        else:
            abi = get_abi_for_address(address, network=network)

        if not abi:
            raise RuntimeError("No se pudo resolver la ABI para el contrato")

        feats = _extract_features(w3, address, abi)

        ia_input = {
            "feature1": float(feats.get("write_ratio", 0.0)),
            "feature2": float(feats.get("risky_flags", 0.0)),
        }
        ia = risk_score(ia_input)
        score = float(ia.get("risk_score", 0.0))
        level = _level_from_score(score)

        summary = {
            "address": address,
            "network": network,
            "name": feats.get("name"),
            "symbol": feats.get("symbol"),
            "decimals": feats.get("decimals"),
            "code_len": feats.get("code_len"),
            "total_functions": feats.get("total_functions"),
        }

        audit.ai_score = score
        audit.risk_level = level
        audit.summary = summary
        audit.features = feats
        audit.details = {"ia_raw": ia}
        audit.status = "done"
        audit.finished_at = datetime.utcnow()
        db.session.commit()

        job.status = "done"
        job.result = {"audit_id": audit.id, "ai_score": score, "risk_level": level}
        db.session.commit()

        return {"ok": True, "audit_id": audit.id, "ai_score": score, "risk_level": level}

    except Exception as e:
        audit.status = "error"
        audit.finished_at = datetime.utcnow()
        db.session.commit()

        job.status = "error"
        job.result = {"error": str(e)}
        db.session.commit()
        raise


def _as_bool(v) -> bool:
    return str(v).lower() in ("1", "true", "yes", "on")
