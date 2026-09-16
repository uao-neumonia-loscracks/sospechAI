"""Spike de acceso a Inference Providers de Hugging Face (R1)."""

from __future__ import annotations

import json
import os
import time
from urllib import error, request

from dotenv import load_dotenv

ROUTER_BASE = "https://router.huggingface.co/v1"
MODEL_ID = "Qwen/Qwen2.5-7B-Instruct:featherless-ai"
PROMPT = "Responde en una sola frase: ¿qué harías esta noche?"


def build_payload(model_id: str, prompt: str) -> dict[str, object]:
    """Construir el cuerpo OpenAI-compatible para una generación corta."""
    return {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.9,
        "max_tokens": 64,
    }


def _headers(token: str) -> dict[str, str]:
    """Encabezados OpenAI-compatible; el router bloquea el UA por defecto."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "sospechai-spike/0.1 (curso UAO 2026-2)",
    }


def call_router(
    token: str, *, model_id: str | None = None
) -> tuple[float, dict[str, object]]:
    """Ejecutar una llamada y devolver (latencia_ms, respuesta JSON)."""
    body = json.dumps(build_payload(model_id or MODEL_ID, PROMPT)).encode("utf-8")
    req = request.Request(
        f"{ROUTER_BASE}/chat/completions",
        data=body,
        headers=_headers(token),
        method="POST",
    )
    started = time.perf_counter()
    try:
        with request.urlopen(req, timeout=30) as response:
            elapsed_ms = (time.perf_counter() - started) * 1000
            payload = json.loads(response.read().decode("utf-8"))
            return elapsed_ms, payload
    except error.HTTPError as http_error:
        elapsed_ms = (time.perf_counter() - started) * 1000
        detail = http_error.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(
            f"HTTP {http_error.code} tras {elapsed_ms:.0f} ms: {detail}"
        ) from None


def list_models(token: str) -> list[str]:
    """Listar los ids de modelo que acepta el router en formato OpenAI."""
    req = request.Request(
        f"{ROUTER_BASE}/models",
        headers=_headers(token),
        method="GET",
    )
    with request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = payload.get("data", [])
    return sorted(
        str(item.get("id", ""))
        for item in data
        if isinstance(item, dict) and item.get("id")
    )


def summarize(
    elapsed_ms: float, payload: dict[str, object], *, model_id: str
) -> dict[str, object]:
    """Reducir la respuesta del router a las métricas que importan a R1."""
    choices = payload.get("choices", [])
    first = choices[0] if isinstance(choices, list) and choices else {}
    message = first.get("message", {}) if isinstance(first, dict) else {}
    text = message.get("content") if isinstance(message, dict) else None
    usage = payload.get("usage", {})
    return {
        "ok": True,
        "model_requested": model_id,
        "model_reported": payload.get("model", ""),
        "latency_ms": round(elapsed_ms, 1),
        "text": text if isinstance(text, str) else "",
        "finish_reason": (
            first.get("finish_reason", "") if isinstance(first, dict) else ""
        ),
        "usage": usage if isinstance(usage, dict) else {},
    }


def main() -> int:
    """Verificar credencial y probar ids de modelo hasta encontrar uno válido."""
    import argparse

    load_dotenv()
    token = os.environ.get("HF_TOKEN", "")
    if not token or not token.startswith("hf_"):
        print("Falta HF_TOKEN válido en .env (debe empezar con hf_).")
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=None, help="Id de modelo a probar")
    parser.add_argument(
        "--list-models", action="store_true", help="Listar ids del router"
    )
    args = parser.parse_args()
    if args.list_models:
        try:
            print("\n".join(list_models(token)))
        except RuntimeError as exc:
            print(str(exc))
            return 1
        return 0
    model_id = args.model or MODEL_ID
    try:
        elapsed_ms, payload = call_router(token, model_id=model_id)
    except RuntimeError as exc:
        print(str(exc))
        if "HTTP 401" in str(exc):
            print("Sospecha: el token en .env está enmascarado o revocado.")
        if "HTTP 404" in str(exc):
            print("Sospecha: el id de modelo no existe en el router.")
        if "HTTP 503" in str(exc):
            print(
                "Proveedor no disponible en este momento; un 503 no prueba arranque en frío."
            )
        return 1
    print(
        json.dumps(
            summarize(elapsed_ms, payload, model_id=model_id),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
