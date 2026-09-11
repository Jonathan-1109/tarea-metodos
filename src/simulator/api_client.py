"""
Integración con Gemini API (google-genai) para análisis automatizado
de los resultados de la simulación.

Usa la Interactions API con un modelo actual (gemini-3.6-flash),
tal como recomienda Google GenAI SDK.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from .report import ANALYSIS_PROMPT

# Modelo vigente según respuesta de la API (2.0-flash ya no está disponible)
DEFAULT_MODEL = "gemini-3.6-flash"


def analyze_with_gemini(report_text: str, api_key: str | None = None) -> str:
    """
    Envía el reporte a Gemini y retorna el texto de análisis.

    Prompt fijo según consignación + contenido del reporte.
    """
    # Cargar .env desde la raíz del proyecto (no solo el cwd)
    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env")
    load_dotenv()  # fallback: cwd

    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key or not key.strip():
        return (
            "[ERROR] GEMINI_API_KEY no configurada. "
            "Copia .env.example a .env y define tu clave."
        )

    try:
        from google import genai
    except ImportError:
        return "[ERROR] Paquete google-genai no instalado. Ejecuta: pip install google-genai"

    prompt = f"{ANALYSIS_PROMPT}\n\n--- REPORTE ---\n{report_text}\n--- FIN ---"

    try:
        client = genai.Client(api_key=key.strip())
        interaction = client.interactions.create(
            model=DEFAULT_MODEL,
            input=prompt,
        )
        text = getattr(interaction, "output_text", None) or str(interaction)
        return text.strip() if text else "[Sin respuesta de la API]"
    except Exception as exc:  # noqa: BLE001 — mostrar el error al usuario
        return f"[ERROR al llamar Gemini API] {exc}"


def analyze_report_file(path: str | Path = "reporte_simulacion.txt") -> str:
    """Lee el archivo de reporte y solicita el análisis a Gemini."""
    report_path = Path(path)
    if not report_path.exists():
        return f"[ERROR] No existe el archivo {report_path}"
    return analyze_with_gemini(report_path.read_text(encoding="utf-8"))
