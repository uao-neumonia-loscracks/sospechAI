"""Benchmark de latencias del router de Hugging Face (R1)."""

from __future__ import annotations

import json
import math
import os
import statistics
import time
from urllib import error, request

from dotenv import load_dotenv

ROUTER_BASE = "https://router.huggingface.co/v1"
MODEL_ID = "Qwen/Qwen2.5-7B-Instruct:featherless-ai"
PROMPT = "Responde en una sola frase: ¿qué harías esta noche?"
SAMPLES = 30
WARMUP = 3
REQUEST_TIMEOUT = 30.0


def build_payload() -> dict[str, object]:
    """Pedir streaming para poder medir el tiempo hasta el primer token."""
    return {
        "model": MODEL_ID,
        "messages": [{"role": "user", "content": PROMPT}],
        "temperature": 0.9,
        "max_tokens": 64,
        "stream": True,
        "stream_options": {"include_usage": True},
    }


def _headers(token: str) -> dict[str, str]:
    """Encabezados OpenAI-compatible; el router bloquea el UA por defecto."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "sospechai-benchmark/0.1 (curso UAO 2026-2)",
    }


def call_streaming(token: str) -> dict[str, object]:
    """Una llamada en streaming; mide TTFT, total y tokens, o registra el error."""
    body = json.dumps(build_payload()).encode("utf-8")
    req = request.Request(
        f"{ROUTER_BASE}/chat/completions",
        data=body,
        headers=_headers(token),
        method="POST",
    )
    started = time.perf_counter()
    ttft_ms: float | None = None
    total_ms = 0.0
    text_parts: list[str] = []
    last_usage: dict[str, object] = {}
    finished = False
    try:
        with request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                if ttft_ms is None:
                    ttft_ms = (time.perf_counter() - started) * 1000
                data = line[5:].strip()
                if data == "[DONE]":
                    finished = True
                    break
                event = json.loads(data)
                usage = event.get("usage")
                if isinstance(usage, dict):
                    last_usage = usage
                choices = event.get("choices", [])
                if not isinstance(choices, list) or not choices:
                    continue
                delta = choices[0].get("delta", {})
                if isinstance(delta, dict) and delta.get("content"):
                    text_parts.append(str(delta["content"]))
            total_ms = (time.perf_counter() - started) * 1000
    except error.HTTPError as http_error:
        total_ms = (time.perf_counter() - started) * 1000
        detail = http_error.read().decode("utf-8", errors="replace")[:200]
        return {
            "error": f"HTTP {http_error.code}: {detail}",
            "ttft_ms": None,
            "total_ms": round(total_ms, 1),
            "tokens": 0,
            "finished": False,
            "text": "",
        }
    return {
        "error": None,
        "ttft_ms": round(ttft_ms or 0.0, 1),
        "total_ms": round(total_ms, 1),
        "tokens": int(last_usage.get("completion_tokens", 0) or 0),
        "finished": finished,
        "text": "".join(text_parts),
    }


def percentile(sorted_values: list[float], p: float) -> float | None:
    """Cuartil por el criterio del plan: ceil(p * n) - 1 en índice 0."""
    if not sorted_values:
        return None
    index = math.ceil(p * len(sorted_values)) - 1
    return sorted_values[index]


def summarize(values: list[float], label: str) -> dict[str, float | None]:
    """p50, p95, mínimo y máximo de una lista de medidas."""
    if not values:
        return {
            f"p50_{label}": None,
            f"p95_{label}": None,
            f"min_{label}": None,
            f"max_{label}": None,
            f"mean_{label}": None,
        }
    ordered = sorted(values)
    return {
        f"p50_{label}": percentile(ordered, 0.5),
        f"p95_{label}": percentile(ordered, 0.95),
        f"min_{label}": ordered[0],
        f"max_{label}": ordered[-1],
        f"mean_{label}": round(statistics.mean(values), 1),
    }


def main() -> int:
    """Calentar el endpoint, medir las muestras y reportar percentiles."""
    load_dotenv()
    token = os.environ.get("HF_TOKEN", "")
    if not token or not token.startswith("hf_"):
        print("Falta HF_TOKEN valido en .env (debe empezar con hf_).")
        return 1
    rows: list[dict[str, object]] = []
    for phase, count in (("warmup", WARMUP), ("muestra", SAMPLES)):
        for i in range(count):
            row = call_streaming(token)
            error = row["error"]
            if error is not None:
                print(f"{phase} {i + 1}/{count} ERROR: {error}", flush=True)
                if "HTTP 402" in str(error):
                    print(
                        "Credito mensual agotado: se aborta el benchmark sin reintentar."
                    )
                    _report(rows)
                    return 1
            else:
                print(f"{phase} {i + 1}/{count} ok", flush=True)
                if phase == "muestra":
                    rows.append(row)
    return _report(rows)


def _report(rows: list[dict[str, object]]) -> int:
    """Imprimir el resumen y devolver el código de salida."""
    ttft = [float(r["ttft_ms"]) for r in rows if r["error"] is None and r["ttft_ms"]]
    total = [float(r["total_ms"]) for r in rows if r["error"] is None]
    errors = [r for r in rows if r["error"] is not None]
    summary: dict[str, object] = {
        "model": MODEL_ID,
        "muestras": SAMPLES,
        "warmup": WARMUP,
        "exitosas": len(total),
        "errores": len(errors),
        "finished": sum(1 for r in rows if r["finished"]),
        "tokens_promedio": (
            round(
                statistics.mean(float(r["tokens"]) for r in rows if r["error"] is None),
                1,
            )
            if total
            else 0
        ),
    }
    summary.update(summarize(total, "total_ms"))
    summary.update(summarize(ttft, "ttft_ms"))
    summary["errores_detalle"] = errors
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if errors and not total else 0


if __name__ == "__main__":
    raise SystemExit(main())
