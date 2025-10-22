# app/services/ai_service.py
import os
import joblib
import numpy as np
from typing import Dict, Any
from sklearn.ensemble import IsolationForest

_MODEL = None

def _train_default_model() -> IsolationForest:
    rng = np.random.RandomState(42)
    # Datos normales ~ N(0,1), 2 features (ejemplo)
    X = rng.normal(0, 1, size=(1000, 2))
    model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
    model.fit(X)
    return model

def _load_or_init_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL

    path = os.getenv("AI_MODEL_PATH")  # opcional: /app/models_store/risk_isoforest.joblib
    if path and os.path.exists(path):
        _MODEL = joblib.load(path)
    else:
        _MODEL = _train_default_model()
    return _MODEL

def risk_score(features: Dict[str, Any]) -> Dict[str, Any]:
    """
    features: dict con keys numéricas. Ej: {"feature1": 0.7, "feature2": -0.1}
    """
    model = _load_or_init_model()

    # Extrae 2 features numéricas simples para demo
    f1 = float(features.get("feature1", 0.0))
    f2 = float(features.get("feature2", 0.0))
    X = np.array([[f1, f2]])

    # IsolationForest -> menor score = más anómalo; invertimos para "riesgo"
    score = -float(model.score_samples(X)[0])  # mayor = más riesgo
    # normaliza a 0..1 de forma simple
    risk = 1 / (1 + np.exp(-score))  # sigmoide

    return {
        "risk_score": round(risk, 4),
        "raw": round(score, 4),
        "features_used": {"feature1": f1, "feature2": f2},
        "model": "IsolationForest",
        "source": "default" if not os.getenv("AI_MODEL_PATH") else "file",
    }
