# StudyFlow AI

Pipeline local (Ollama) que convierte apuntes, PDFs, presentaciones y audio en material de
estudio: explicaciones por subtema, flashcards y preguntas tipo test, todo en un único
`index.html`.

A diferencia de un pipeline "todo de una vez", StudyFlow mantiene un **índice de temas
persistente por proyecto** que va creciendo documento a documento — puedes ir añadiendo apuntes
sueltos a lo largo del cuatrimestre y el sistema decide dónde encaja cada uno, sin volver a
procesar lo que ya estaba clasificado.

---

## Flujo general

```
documentos (PDF/DOCX/PPTX/TXT/audio)
        │
        ▼
  1. Extracción de texto  (consumption/extractor.py)
        │
        ▼
  2. Troceado por estructura interna  (process/chunker.py)
        │   un documento largo con "Tema 1", "Tema 2"... se divide
        │   en secciones ANTES de clasificar
        ▼
  3. Clasificación incremental  (process/classifier.py)
        │   cada sección se enruta a un tema/subtema del índice
        │   del proyecto (crea uno nuevo si no encaja en ninguno)
        ▼
  4. index.json  (utils/project.py)
        │   {"topics": [{"id","title","subtopics":[{"id","title",
        │                "content","sources"}]}]}
        ▼
  5. Generación de material  (generator/content.py)
        │   explicación + conceptos + preguntas + flashcards
        │   por subtema, con reutilización de temas sin cambios
        ▼
  6. material.json + output/index.html  (generator/html_builder.py)
```

## El índice persistente: clasificación por 3 prompts

En vez de analizar todo el texto de golpe y pedirle al LLM "dame entre 3 y 8 temas" (lo cual
fragmentaba documentos largos en temas casi-duplicados), cada trozo de documento pasa por tres
llamadas especializadas, inspiradas en un pipeline de lector/enrutador/redactor:

1. **El Lector** (`_read_document`) — extrae si el propio texto declara explícitamente un
   tema/subtema ("Tema 1: X"), o en su defecto una estimación, más una lista de conceptos clave.
2. **El Enrutador** (`_route_document`) — con el índice actual del proyecto a la vista, decide:
   reutilizar un subtema existente, crear un subtema nuevo dentro de un tema existente, o crear un
   tema completamente nuevo. Prioriza guía explícita > pertenencia lógica > disciplina sobre
   sujeto superficial, y evita duplicados.
3. **El Redactor** (`_merge_content`) — si el subtema elegido ya tenía contenido de documentos
   anteriores, fusiona el texto nuevo sin duplicar ideas ya cubiertas.

No hay ningún catálogo de temas fijo en ningún sitio: todos los títulos salen de los documentos
mismos (guía explícita) o del juicio del modelo contra lo que ya existe en el índice. Esto es
intencional — el sistema debe servir para apuntes de cualquier asignatura.

### Vía rápida sin LLM (fast route)

Antes de gastar una llamada al modelo, `classify_document` intenta dos atajos baratos:

- **Por nombre de archivo**: si el archivo se llama, por ejemplo, `Tema_2_Probabilidad.pdf` y ya
  existe un tema "Tema 2 Probabilidad" en el índice, se usa directamente.
- **Por contenido inicial**: si no hay pista en el nombre, compara el encabezado detectado (o los
  primeros ~500 caracteres) contra los títulos existentes.

Solo actúa con una similitud ≥ 90% (`FAST_MATCH_THRESHOLD` en `config.py`) — con cualquier duda,
cae al flujo normal con LLM. Si además del tema también identifica el subtema con esa confianza,
se salta el Lector *y* el Enrutador enteros; si solo identifica el tema, se salta el Lector y usa
un Enrutador más ligero acotado a los subtemas de ese tema. El ahorro solo aparece a partir del
segundo documento de un proyecto en adelante — el primero siempre necesita el flujo completo,
porque no hay nada contra qué comparar todavía.

### Troceado de documentos largos (`process/chunker.py`)

Un documento de 45 páginas con su propio índice interno ("Tema 1"..."Tema 12") se divide en
secciones **antes** de llegar al clasificador, para que cada sección se clasifique — y genere
contenido — de forma independiente. Sin esto, todo el documento se colapsaba en un único
tema/subtema, y `content.py` solo llegaba a usar los primeros 8000 caracteres del texto fusionado.

- Busca encabezados con varios patrones a la vez: numerados (`"3. Tema 1: X"`, `"6.1. Y"`),
  en mayúsculas (`"TEMA 1: X"`), o estilo markdown (`"# Título"`).
- Si detecta una estructura poco fiable (menos de 2 encabezados, o uno que se traga más del 70%
  del documento), cae a un troceado por tamaño (~6000 caracteres, respetando párrafos) y deja que
  el Lector/Enrutador decidan la agrupación sin ninguna pista de título.

### Saturación

Un subtema que crece demasiado (por defecto, más de 9000 caracteres o más de 4 documentos
integrados — `SATURATION_CHAR_THRESHOLD` / `SATURATION_DOC_THRESHOLD` en `config.py`) se
promociona automáticamente a tema propio, para que no siga engordando indefinidamente dentro de
su tema original.

> **Nota sobre el umbral de caracteres**: `generator/content.py` trunca el contenido de un
> subtema a sus primeros 8000 caracteres al generar explicación/preguntas/flashcards. Si el
> umbral de saturación se sube muy por encima de eso, la cola del contenido nunca llega a
> generarse aunque esté guardada en el índice.

### Red de seguridad contra duplicados por tildes/mayúsculas

Independientemente de lo que decida el LLM, antes de crear un tema o subtema "nuevo" se compara
(normalizado: sin tildes, minúsculas) contra los ya existentes con similitud difusa
(`DUPLICATE_TITLE_SIMILARITY = 0.87` por defecto). Evita que "Estadística" y "ESTADISTICA" acaben
como dos temas distintos por un desliz del modelo.

### Regeneración parcial

El material generado (explicaciones, preguntas, flashcards) se guarda en `material.json`, no solo
el HTML final. Cuando se añaden documentos nuevos a un proyecto existente, el pipeline calcula qué
temas se vieron realmente afectados (por clasificación o por una promoción de saturación) y **solo
regenera esos** — los demás se copian tal cual del `material.json` anterior, sin volver a llamar
al LLM.

---

## Estructura de un proyecto

```
projects/<nombre>/
├── project.json      metadatos (archivos añadidos, fechas)
├── index.json         índice de temas/subtemas persistente
├── material.json       último material generado (para regeneración parcial)
├── documents/          archivos originales subidos
├── extracted/           texto plano extraído de cada archivo
├── logs/pipeline.log     log estructurado JSONL de la ejecución
├── .cache/llm/            caché de respuestas del LLM (por hash de prompt)
└── output/
    ├── index.html          material de estudio final
    └── index.pdf            (opcional, si se pide export_pdf=True)
```

## Uso

```python
from pipeline import run

run(
    project_name="stats_t1",
    files=["notas.pdf", "clase_grabada.mp3"],
    questions_per_topic=8,
    export_pdf=False,
)
```

O de forma interactiva:

```bash
python pipeline.py
```

## Herramientas de inspección y corrección manual

```bash
# Ver el índice de temas/subtemas de un proyecto
python inspect_index.py mi_proyecto

# Igual, con preview del contenido de cada subtema
python inspect_index.py mi_proyecto --full

# Reasignar manualmente un documento mal clasificado
python inspect_index.py mi_proyecto --move archivo.pdf tema_destino_id --subtopic "Título del subtema"
```

`--move` funciona tanto con documentos sin dividir como con secciones de un documento troceado
(`archivo.pdf#3`) — en ese caso vuelve a trocear el archivo original para recuperar el texto exacto
de esa sección. Si la sección compartía subtema con otros documentos, su contenido ya fusionado no
se puede separar retroactivamente con precisión (el Redactor no rastrea qué frase vino de qué
documento) — el aviso en pantalla lo indica.

## Configuración (`config.py` / `.env`)

| Variable | Por defecto | Qué hace |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Endpoint de Ollama |
| `OLLAMA_MODEL` | `llama3.2` | Modelo por defecto |
| `OLLAMA_TIMEOUT` | `900` | Timeout (segundos) por llamada — modelos grandes en CPU pueden necesitar más |
| `PROJECTS_DIR` | `./projects` | Dónde viven los proyectos |
| `SATURATION_CHAR_THRESHOLD` | `9000` | Tamaño de subtema que dispara la promoción a tema |
| `SATURATION_DOC_THRESHOLD` | `4` | Nº de documentos en un subtema que dispara la promoción |
| `DUPLICATE_TITLE_SIMILARITY` | `0.87` | Umbral de similitud para evitar temas/subtemas duplicados |
| `FAST_MATCH_THRESHOLD` | `0.90` | Umbral de similitud para saltarse el LLM en la vía rápida |
| `INDEX_SUMMARY_MAX_SUBTOPICS` | `10` | Máximo de subtemas listados por tema al prompt del Enrutador |

## Tests

```bash
pytest tests/test_classifier.py -v
```

Cubre la lógica de clasificación con un LLM simulado (`FakeLLM`) — no depende de Ollama real.
Verifica: creación desde índice vacío, manejo de un `topic_id` alucinado por el modelo, fusión y
no-duplicado de fuentes, fallo del Redactor sin pérdida de contenido, saturación por tamaño y por
nº de documentos, y la red de seguridad contra duplicados por tildes/mayúsculas.

## Limitaciones conocidas

- **La regeneración parcial y la vía rápida de clasificación no se han probado de punta a punta
  contra Ollama real** — solo verificadas con un LLM simulado. Antes de confiar en ellas en un
  proyecto importante, conviene correr el pipeline dos veces sobre un proyecto de prueba (crear +
  añadir un documento) y revisar `index.json` / `material.json` resultantes.
- El troceado por tamaño (cuando no hay estructura de encabezados detectable) no tiene ninguna
  noción semántica — corta por párrafos hasta llegar a ~6000 caracteres, sin más criterio.
- `move_document`/`--move` no puede separar con precisión el contenido de un documento que
  compartió subtema con otros — solo lo saca de la lista de fuentes y lo añade en el nuevo
  destino; el contenido histórico fusionado no se reescribe automáticamente.