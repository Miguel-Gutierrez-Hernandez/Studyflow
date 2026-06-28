"""
generador/contenido.py — Generación de material de estudio con LLM.

Por cada tema detectado genera:
    - resumen estructurado
    - palabras clave y conceptos importantes
    - trucos de memorización
    - preguntas tipo test con 4 opciones, respuesta y explicación

Uso:
    from generador.contenido import generar_material
    material = generar_material(analisis, llm)
"""

from __future__ import annotations

import json
import re

from core.llm import BaseLLM, get_llm


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM = """Eres un profesor experto en crear material de estudio efectivo.
Tu especialidad es convertir apuntes académicos en recursos de repaso claros,
con explicaciones pedagógicas, trucos de memorización y preguntas de examen.
Siempre respondes en JSON válido, sin texto adicional fuera del JSON.
El idioma es español."""


# ── Prompts por sección ───────────────────────────────────────────────────────

def _prompt_resumen(tema: dict, texto_completo: str) -> str:
    contexto = texto_completo[:8000] if len(texto_completo) > 8000 else texto_completo
    return f"""Genera un resumen de estudio para el siguiente tema.

TEMA: {tema['titulo']}
SUBTEMAS: {', '.join(tema.get('subtemas', []))}
CONTEXTO DEL MATERIAL:
{contexto}

Devuelve SOLO este JSON (sin ```json ni texto extra):
{{
  "resumen": "Explicación completa del tema en 3-6 párrafos. Incluye definiciones clave, conceptos importantes y relaciones entre ideas. Usa un tono pedagógico claro.",
  "puntos_clave": ["punto 1", "punto 2", "punto 3", "punto 4", "punto 5"],
  "palabras_clave": [
    {{"termino": "Término", "definicion": "Definición breve y precisa"}}
  ],
  "trucos_memoria": [
    {{"truco": "Descripción del truco o mnemónico", "ejemplo": "Ejemplo de aplicación"}}
  ]
}}

- El resumen debe cubrir todos los subtemas
- Incluye entre 5-8 palabras clave con definición
- Incluye 2-4 trucos de memorización o mnemónicos útiles
- Los puntos clave deben ser frases completas y accionables"""


def _prompt_preguntas(tema: dict, texto_completo: str, n_preguntas: int = 8) -> str:
    contexto = texto_completo[:8000] if len(texto_completo) > 8000 else texto_completo
    return f"""Genera {n_preguntas} preguntas tipo test para el tema indicado.

TEMA: {tema['titulo']}
SUBTEMAS: {', '.join(tema.get('subtemas', []))}
CONTEXTO DEL MATERIAL:
{contexto}

Devuelve SOLO este JSON (sin ```json ni texto extra):
{{
  "preguntas": [
    {{
      "pregunta": "Enunciado claro de la pregunta",
      "opciones": ["Opción A", "Opción B", "Opción C", "Opción D"],
      "respuesta_correcta": 0,
      "explicacion": "Por qué esta respuesta es correcta y por qué las otras no."
    }}
  ]
}}

Reglas:
- respuesta_correcta es el índice (0, 1, 2 o 3) de la opción correcta
- Las opciones incorrectas deben ser plausibles, no obviamente falsas
- La explicación debe ser educativa y completa (2-3 frases)
- Varía el nivel: conceptual, aplicación y análisis
- No repitas preguntas similares"""


# ── Función de parseo seguro ───────────────────────────────────────────────────

def _parsear_json(respuesta: str, fallback: dict) -> dict:
    """Intenta parsear JSON de la respuesta del LLM, con fallback."""
    texto = respuesta.strip()
    # Eliminar bloques de código si el modelo los añade
    if "```" in texto:
        match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", texto)
        if match:
            texto = match.group(1)
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        # Intentar extraer JSON entre { }
        match = re.search(r"\{[\s\S]+\}", texto)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return fallback


# ── Generación por tema ───────────────────────────────────────────────────────

def generar_tema(
    tema: dict,
    texto_completo: str,
    llm: BaseLLM,
    n_preguntas: int = 8,
) -> dict:
    """
    Genera todo el material de estudio para un tema.

    Returns:
        Dict con resumen, palabras_clave, trucos_memoria, puntos_clave y preguntas.
    """
    print(f"    📝 Generando resumen y conceptos para: {tema['titulo']}")
    resp_resumen = llm.chat(
        _prompt_resumen(tema, texto_completo),
        system=_SYSTEM,
        max_tokens=2500,
        temperature=0.4,
    )
    datos_resumen = _parsear_json(resp_resumen, {
        "resumen": tema.get("contenido_relevante", ""),
        "puntos_clave": [],
        "palabras_clave": [],
        "trucos_memoria": [],
    })

    print(f"    ❓ Generando preguntas test para: {tema['titulo']}")
    resp_preguntas = llm.chat(
        _prompt_preguntas(tema, texto_completo, n_preguntas),
        system=_SYSTEM,
        max_tokens=3000,
        temperature=0.5,
    )
    datos_preguntas = _parsear_json(resp_preguntas, {"preguntas": []})

    return {
        "id": tema["id"],
        "titulo": tema["titulo"],
        "subtemas": tema.get("subtemas", []),
        "resumen": datos_resumen.get("resumen", ""),
        "puntos_clave": datos_resumen.get("puntos_clave", []),
        "palabras_clave": datos_resumen.get("palabras_clave", []),
        "trucos_memoria": datos_resumen.get("trucos_memoria", []),
        "preguntas": datos_preguntas.get("preguntas", []),
    }


# ── Pipeline completo ─────────────────────────────────────────────────────────

def generar_material(
    analisis: dict,
    llm: BaseLLM | None = None,
    n_preguntas_por_tema: int = 8,
) -> dict:
    """
    Genera material completo para todos los temas del análisis.

    Args:
        analisis: Salida de procesado.analizador.analizar()
        llm: Instancia del LLM. Si None, usa el configurado en .env.
        n_preguntas_por_tema: Preguntas test por tema.

    Returns:
        Dict con toda la información necesaria para generar el HTML.
    """
    llm = llm or get_llm()

    titulo = analisis["titulo"]
    temas = analisis["temas"]
    texto_completo = analisis["texto_completo"]
    fuentes = analisis.get("fuentes", [])

    print(f"\n  🎓 Generando material para '{titulo}' ({len(temas)} temas)...")

    temas_generados = []
    for i, tema in enumerate(temas, 1):
        print(f"\n  [{i}/{len(temas)}] {tema['titulo']}")
        tema_material = generar_tema(
            tema,
            texto_completo,
            llm,
            n_preguntas=n_preguntas_por_tema,
        )
        temas_generados.append(tema_material)

    total_preguntas = sum(len(t["preguntas"]) for t in temas_generados)

    return {
        "titulo": titulo,
        "temas": temas_generados,
        "fuentes": fuentes,
        "stats": {
            "n_temas": len(temas_generados),
            "n_preguntas": total_preguntas,
        },
    }
