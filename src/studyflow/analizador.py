"""
procesado/analizador.py — Limpieza, estructuración y análisis del contenido.

Pasos:
    1. limpiar_texto()   → normaliza el texto crudo extraído
    2. detectar_temas()  → usa el LLM para identificar temas y subtemas
    3. analizar()        → pipeline completo, devuelve un dict estructurado

El dict de salida tiene esta forma:
    {
        "titulo": "Nombre del documento / asignatura",
        "temas": [
            {
                "id": "tema_1",
                "titulo": "Título del tema",
                "contenido": "Texto relevante del tema",
                "subtemas": ["subtema A", "subtema B"]
            },
            ...
        ],
        "texto_completo": "..."   ← texto limpio concatenado
    }
"""

from __future__ import annotations

import json
import re

from core.llm import BaseLLM, get_llm


# ── Limpieza de texto ─────────────────────────────────────────────────────────

def limpiar_texto(texto: str) -> str:
    """
    Normaliza el texto extraído:
    - Elimina líneas vacías excesivas
    - Corrige espaciado alrededor de puntuación
    - Elimina caracteres de control extraños
    - Preserva saltos de párrafo significativos
    """
    # Eliminar caracteres de control excepto saltos de línea y tabulaciones
    texto = re.sub(r"[^\S\n\t ]+", " ", texto)

    # Normalizar tabulaciones a espacios
    texto = texto.replace("\t", "  ")

    # Eliminar espacios al inicio/fin de cada línea
    lineas = [l.rstrip() for l in texto.split("\n")]

    # Colapsar más de 2 líneas vacías consecutivas en 2
    resultado = []
    vacias_consecutivas = 0
    for linea in lineas:
        if linea.strip() == "":
            vacias_consecutivas += 1
            if vacias_consecutivas <= 2:
                resultado.append("")
        else:
            vacias_consecutivas = 0
            resultado.append(linea)

    return "\n".join(resultado).strip()


def limpiar_multiples(textos: dict[str, str]) -> str:
    """
    Limpia y concatena múltiples textos (de distintos archivos) en uno solo.
    Añade separadores para que el LLM sepa de dónde viene cada fragmento.
    """
    partes = []
    for nombre, texto in textos.items():
        if texto.startswith("[ERROR:"):
            continue  # saltar archivos con error
        texto_limpio = limpiar_texto(texto)
        if texto_limpio:
            partes.append(f"=== Fuente: {nombre} ===\n\n{texto_limpio}")
    return "\n\n" + "─" * 60 + "\n\n".join(partes)


# ── Prompts ───────────────────────────────────────────────────────────────────

_SYSTEM_ANALISIS = """Eres un asistente experto en organizar material de estudio.
Tu objetivo es analizar contenido académico y estructurarlo de forma clara y útil.
Siempre respondes en JSON válido, sin texto adicional fuera del JSON.
El idioma del contenido es español."""


def _prompt_detectar_temas(texto: str, max_temas: int = 10) -> str:
    # Truncamos para no exceder contexto en modelos pequeños
    texto_truncado = texto[:12000] if len(texto) > 12000 else texto
    return f"""Analiza el siguiente contenido académico y extrae su estructura temática.

CONTENIDO:
{texto_truncado}

Devuelve SOLO un JSON con esta estructura exacta (sin ```json ni texto extra):
{{
  "titulo": "Título descriptivo del material (asignatura o tema general)",
  "temas": [
    {{
      "id": "tema_1",
      "titulo": "Título del tema",
      "subtemas": ["subtema 1", "subtema 2"],
      "contenido_relevante": "Resumen de 2-4 frases del contenido principal de este tema"
    }}
  ]
}}

Reglas:
- Máximo {max_temas} temas
- Los temas deben ser coherentes y bien diferenciados
- Los ids deben ser tema_1, tema_2, tema_3...
- Si el contenido es de un solo tema, crea sub-secciones como temas separados"""


# ── Análisis con LLM ──────────────────────────────────────────────────────────

def detectar_temas(texto: str, llm: BaseLLM | None = None) -> dict:
    """
    Usa el LLM para detectar la estructura temática del texto.

    Returns:
        Dict con 'titulo' y lista de 'temas'
    """
    llm = llm or get_llm()
    prompt = _prompt_detectar_temas(texto)

    respuesta = llm.chat(prompt, system=_SYSTEM_ANALISIS, max_tokens=2000)

    # Intentar parsear el JSON de la respuesta
    try:
        # Limpiar posibles artefactos del LLM
        respuesta_limpia = respuesta.strip()
        if "```" in respuesta_limpia:
            # Extraer JSON de bloques de código si el modelo los añade
            match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", respuesta_limpia)
            if match:
                respuesta_limpia = match.group(1)
        return json.loads(respuesta_limpia)
    except json.JSONDecodeError as e:
        # Si falla el parse, devolver estructura mínima de fallback
        print(f"  ⚠️  Error parseando JSON del LLM: {e}")
        print(f"  Respuesta recibida: {respuesta[:200]}...")
        return {
            "titulo": "Material de estudio",
            "temas": [
                {
                    "id": "tema_1",
                    "titulo": "Contenido general",
                    "subtemas": [],
                    "contenido_relevante": texto[:500],
                }
            ],
        }


def analizar(
    textos: dict[str, str],
    llm: BaseLLM | None = None,
) -> dict:
    """
    Pipeline completo de análisis.

    Args:
        textos: Dict {nombre_archivo: texto_extraido} (salida de extraer_todos)
        llm: Instancia de BaseLLM. Si None, usa el configurado en .env.

    Returns:
        Dict con título, temas y texto completo limpio.
    """
    llm = llm or get_llm()

    print("  🧹 Limpiando y concatenando textos...")
    texto_completo = limpiar_multiples(textos)

    print("  🔍 Detectando estructura temática con LLM...")
    estructura = detectar_temas(texto_completo, llm=llm)

    return {
        "titulo": estructura.get("titulo", "Material de estudio"),
        "temas": estructura.get("temas", []),
        "texto_completo": texto_completo,
        "fuentes": list(textos.keys()),
    }
