# StudyFlow AI

Plataforma inteligente para transformar apuntes, clases y documentos en material de estudio estructurado.

## Estructura del proyecto

```
studyflow/
├── config.py                  ← Configuración central (lee el .env)
├── pipeline.py                ← Orquestador principal (punto de entrada)
├── requirements.txt
├── .env.example               ← Copia esto a .env y rellena tus claves
│
├── core/
│   └── llm.py                 ← Módulo LLM agnóstico (HF / OpenAI / Anthropic / Ollama)
│
├── ingesta/
│   └── extractor.py           ← Extracción de texto (PDF, DOCX, PPTX, TXT, audio)
│
├── procesado/
│   └── analizador.py          ← Limpieza, detección de temas con LLM
│
├── generador/
│   ├── contenido.py           ← Resumen, palabras clave, trucos, preguntas test
│   └── html_builder.py        ← Generador del HTML final navegable
│
└── utils/
    └── proyecto.py            ← Gestión de estructura de carpetas por proyecto
```

### Estructura de un proyecto generado

```
proyectos/
└── nombre_proyecto/
    ├── proyecto.json           ← Metadatos (nombre, fecha, documentos)
    ├── documentos/             ← Archivos originales subidos
    ├── procesado/              ← Textos extraídos (.txt por archivo)
    └── output/
        └── index.html          ← HTML final de repaso
```

## Instalación

### 1. Requisitos del sistema

- Python 3.11+
- ffmpeg (necesario para Whisper y audio)

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows
# Descarga desde https://ffmpeg.org/download.html y añade al PATH
```

### 2. Instalar dependencias Python

```bash
cd studyflow
pip install -r requirements.txt
```

### 3. Configurar el entorno

```bash
cp .env.example .env
# Edita .env con tu token de HuggingFace y la configuración que necesites
```

El `.env` mínimo para empezar con HuggingFace:
```
LLM_PROVIDER=huggingface
HF_TOKEN=hf_tu_token_aqui
HF_MODEL=meta-llama/Llama-3.1-8B-Instruct
WHISPER_MODEL=small
PROYECTOS_DIR=./proyectos
```

## Uso

### Modo interactivo (CLI)

```bash
python pipeline.py
```

Te pedirá el nombre del proyecto, los archivos y el número de preguntas.

### Desde código

```python
from pipeline import ejecutar

ruta_html = ejecutar(
    nombre_proyecto="estadistica_T1",
    archivos=[
        "apuntes.pdf",
        "diapositivas.pptx",
        "clase_grabada.mp3",
    ],
    n_preguntas_por_tema=10,
)
print(f"HTML generado en: {ruta_html}")
```

### Añadir contenido a un proyecto existente

```python
from pipeline import ejecutar

# Añadir nuevos apuntes a un proyecto ya existente
# El HTML se regenera con todo el contenido (anterior + nuevo)
ruta_html = ejecutar(
    nombre_proyecto="estadistica_T1",
    archivos=["tema2_nuevos_apuntes.pdf"],
    sobrescribir_proyecto=False,  # False = añade, no sobreescribe
)
```

### Cambiar de LLM provider

```python
from pipeline import ejecutar

# Usar OpenAI en lugar de HuggingFace
ruta_html = ejecutar(
    nombre_proyecto="mi_proyecto",
    archivos=["apuntes.pdf"],
    llm_provider="openai",  # requiere OPENAI_API_KEY en .env
)
```

## Formatos soportados

| Formato | Extensiones |
|---------|-------------|
| PDF | `.pdf` |
| Word | `.docx` |
| PowerPoint | `.pptx` |
| Texto plano | `.txt` |
| Audio (transcripción) | `.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac` |

## LLM Providers

| Provider | Variable en .env | Modelo por defecto |
|----------|-----------------|-------------------|
| HuggingFace | `HF_TOKEN` | `meta-llama/Llama-3.1-8B-Instruct` |
| OpenAI | `OPENAI_API_KEY` | `gpt-4o-mini` |
| Anthropic | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` |
| Ollama (local) | — | `llama3.1` |

## HTML generado

El HTML de salida incluye:

- **Resumen estructurado** por temas con puntos clave
- **Palabras clave** con definición para cada tema
- **Trucos de memorización** y mnemónicos
- **Test interactivo** por tema con feedback inmediato
- **Flashcards** giratorias organizadas por tema
- **Modo examen** con preguntas mezcladas, configuración de número y desglose por tema
- **Navegación sticky** entre secciones

## Roadmap

- [x] MVP Fase 1: ingesta, procesado, generación y HTML
- [ ] Fase 2: guardado de proyectos con historial, modo repaso
- [ ] Fase 3: MLflow tracking, distillation, comparación de prompts