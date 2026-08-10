"""
generador/html_builder.py — Genera el HTML final de repaso.

Estilo basado en la guía de referencia: tarjetas modernas, navegación sticky,
flashcards, preguntas test con feedback inmediato y modo examen.

Uso:
    from generador.html_builder import generar_html
    html = generar_html(material)
"""

from __future__ import annotations

import json
from datetime import datetime


def generar_html(material: dict) -> str:
    """
    Genera el HTML completo de repaso a partir del material generado.

    Args:
        material: Salida de generador.contenido.generar_material()

    Returns:
        String con el HTML completo listo para guardar.
    """
    titulo = material["titulo"]
    temas = material["temas"]
    fuentes = material.get("fuentes", [])
    stats = material.get("stats", {})
    fecha = datetime.now().strftime("%d/%m/%Y")

    # Serializar preguntas para JS
    preguntas_js = _serializar_preguntas_js(temas)
    flashcards_js = _serializar_flashcards_js(temas)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{titulo} — StudyFlow AI</title>
{_css()}
</head>
<body>

<header>
  <div class="hero">
    <div class="hero-card">
      <div class="sf-badge">⚡ StudyFlow AI</div>
      <h1>{titulo}</h1>
      <p class="subtitle">Material de estudio generado automáticamente · {fecha}</p>
      <div class="badges">
        {"".join(f'<span class="badge">{t["titulo"]}</span>' for t in temas)}
        {"".join(f'<span class="badge source">📄 {f}</span>' for f in fuentes)}
      </div>
    </div>
    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-number">{stats.get("n_temas", len(temas))}</div>
        <div class="stat-label">temas de estudio</div>
      </div>
      <div class="stat-card">
        <div class="stat-number">{stats.get("n_preguntas", 0)}</div>
        <div class="stat-label">preguntas tipo test</div>
      </div>
    </div>
  </div>
</header>

<nav>
  <div class="nav-inner">
    <a class="nav-link" href="#resumen">📋 Resumen</a>
    {"".join(f'<a class="nav-link" href="#{t["id"]}">{t["titulo"]}</a>' for t in temas)}
    <a class="nav-link" href="#flashcards">🃏 Flashcards</a>
    <a class="nav-link" href="#examen">🎓 Examen</a>
  </div>
</nav>

<main>

  {_seccion_resumen_general(temas)}

  {"".join(_seccion_tema(t, i) for i, t in enumerate(temas))}

  {_seccion_flashcards(temas)}

  {_seccion_examen(temas)}

</main>

{_script(preguntas_js, flashcards_js)}

</body>
</html>"""


# ── Secciones HTML ────────────────────────────────────────────────────────────

def _seccion_resumen_general(temas: list[dict]) -> str:
    items = "".join(
        f"""<div class="module">
          <h3><a href="#{t['id']}" class="tema-link">
            <span class="tema-num">{i+1}</span>{t['titulo']}
          </a></h3>
          <p>{" · ".join(t.get("subtemas", [])[:4]) or "Sin subtemas definidos"}</p>
          <div class="pills">
            {"".join(f'<span class="pill">{st}</span>' for st in t.get("subtemas", []))}
          </div>
        </div>"""
        for i, t in enumerate(temas)
    )
    return f"""<section id="resumen">
  <div class="section-title">
    <div>
      <h2>📋 Estructura del material</h2>
      <p>Visión general de todos los temas. Haz clic en cualquier tema para ir directamente.</p>
    </div>
  </div>
  <div class="grid3">{items}</div>
</section>"""


def _seccion_tema(tema: dict, idx: int) -> str:
    tid = tema["id"]
    titulo = tema["titulo"]
    resumen = tema.get("resumen", "")
    puntos = tema.get("puntos_clave", [])
    palabras = tema.get("palabras_clave", [])
    trucos = tema.get("trucos_memoria", [])
    preguntas = tema.get("preguntas", [])

    # Resumen + puntos clave
    puntos_html = "".join(f"<li>{p}</li>" for p in puntos)

    # Palabras clave
    palabras_html = "".join(
        f"""<div class="keyword-card">
          <strong>{kw.get('termino','')}</strong>
          <p>{kw.get('definicion','')}</p>
        </div>"""
        for kw in palabras
    )

    # Trucos de memorización
    trucos_html = "".join(
        f"""<div class="truco">
          <div class="truco-icon">💡</div>
          <div>
            <strong>{tr.get('truco','')}</strong>
            {f'<p class="truco-ejemplo">Ej: {tr.get("ejemplo","")}</p>' if tr.get('ejemplo') else ''}
          </div>
        </div>"""
        for tr in trucos
    )

    # Test interactivo
    preguntas_html = _preguntas_html(tid, preguntas)

    return f"""<section id="{tid}">
  <div class="section-title">
    <div>
      <h2><span class="tema-num-lg">{idx+1}</span>{titulo}</h2>
      {f'<p>{"  ·  ".join(tema.get("subtemas",[]))}</p>' if tema.get("subtemas") else ""}
    </div>
  </div>

  <div class="grid2" style="margin-bottom:14px">
    <div class="panel">
      <h3>📖 Resumen</h3>
      <div class="resumen-texto">{_parrafos(resumen)}</div>
    </div>
    <div class="panel">
      <h3>✅ Puntos clave</h3>
      <ul class="puntos-lista">{puntos_html}</ul>
    </div>
  </div>

  {f'<div class="keywords-section"><h3>🔑 Palabras clave</h3><div class="keywords-grid">{palabras_html}</div></div>' if palabras_html else ''}

  {f'<div class="trucos-section"><h3>🧠 Trucos de memorización</h3><div class="trucos-grid">{trucos_html}</div></div>' if trucos_html else ''}

  {f'<div class="test-section"><h3>❓ Test rápido — {titulo}</h3>{preguntas_html}</div>' if preguntas_html else ''}

</section>"""


def _preguntas_html(tid: str, preguntas: list[dict]) -> str:
    if not preguntas:
        return ""
    cards = ""
    for i, p in enumerate(preguntas):
        qid = f"{tid}_q{i}"
        opciones = "".join(
            f'<div class="quiz-option" onclick="responder(\'{qid}\',{j},{p["respuesta_correcta"]},this,\'{_escapar(p["explicacion"])}\')">'
            f'{chr(97+j)}. {op}</div>'
            for j, op in enumerate(p["opciones"])
        )
        cards += f"""<div class="quiz-card" id="card-{qid}">
          <h3>{i+1}. {p["pregunta"]}</h3>
          <div class="opciones">{opciones}</div>
          <div class="quiz-note" id="note-{qid}"></div>
        </div>"""
    return f'<div class="quiz-grid">{cards}</div>'


def _seccion_flashcards(temas: list[dict]) -> str:
    # Tabs por tema
    tabs = "".join(
        f'<button class="tab{" active" if i==0 else ""}" onclick="switchFlashTab(\'{t["id"]}\',this)">{t["titulo"]}</button>'
        for i, t in enumerate(temas)
    )
    contenido = "".join(
        f'<div class="tab-content{" active" if i==0 else ""}" id="flash-{t["id"]}">'
        f'<div class="flashcards" id="fc-grid-{t["id"]}"></div>'
        f'</div>'
        for i, t in enumerate(temas)
    )
    return f"""<section id="flashcards">
  <div class="section-title">
    <div>
      <h2>🃏 Flashcards</h2>
      <p>Haz clic en cada tarjeta para ver la definición. Repasa por tema.</p>
    </div>
  </div>
  <div class="tabs" style="margin-bottom:14px">{tabs}</div>
  {contenido}
</section>"""


def _seccion_examen(temas: list[dict]) -> str:
    return f"""<section id="examen">
  <div class="section-title">
    <div>
      <h2>🎓 Modo examen</h2>
      <p>Preguntas mezcladas de todos los temas. Configura y empieza cuando estés listo.</p>
    </div>
  </div>
  <div class="panel" style="margin-bottom:14px">
    <div class="exam-toolbar">
      <div class="exam-control">
        <label>Nº preguntas</label>
        <input type="number" id="examCount" value="20" min="5" max="200" style="width:80px">
      </div>
      <label class="toggle-label">
        <input type="checkbox" id="examShuffle" checked> Mezclar orden
      </label>
      <label class="toggle-label">
        <input type="checkbox" id="examShowTopic"> Mostrar tema
      </label>
      <button class="primary" onclick="iniciarExamen()">▶ Iniciar examen</button>
      <button onclick="corregirExamen()">✅ Corregir</button>
      <button onclick="resetExamen()">🔄 Reiniciar</button>
      <div class="score" id="examScore">Sin iniciar</div>
    </div>
  </div>
  <div id="examGrid" class="quiz-grid"></div>
  <div id="examBreakdown" class="result" style="display:none;margin-top:14px"></div>
</section>"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parrafos(texto: str) -> str:
    """Convierte texto con saltos de línea en párrafos HTML."""
    parrafos = [p.strip() for p in texto.split("\n\n") if p.strip()]
    if not parrafos:
        parrafos = [texto]
    return "".join(f"<p>{p}</p>" for p in parrafos)


def _escapar(texto: str) -> str:
    """Escapa texto para uso seguro en atributos JS."""
    return texto.replace("'", "\\'").replace('"', '\\"').replace("\n", " ")


def _serializar_preguntas_js(temas: list[dict]) -> str:
    """Serializa todas las preguntas en formato JS para el modo examen."""
    todas = []
    for t in temas:
        for p in t.get("preguntas", []):
            todas.append({
                "topicId": t["id"],
                "topicName": t["titulo"],
                "q": p["pregunta"],
                "options": p["opciones"],
                "answer": p["respuesta_correcta"],
                "why": p.get("explicacion", ""),
            })
    return json.dumps(todas, ensure_ascii=False)


def _serializar_flashcards_js(temas: list[dict]) -> str:
    """Serializa flashcards por tema en formato JS."""
    por_tema = {}
    for t in temas:
        cards = []
        for kw in t.get("palabras_clave", []):
            cards.append({
                "front": kw.get("termino", ""),
                "back": kw.get("definicion", ""),
            })
        for truco in t.get("trucos_memoria", []):
            if truco.get("truco"):
                cards.append({
                    "front": f"💡 {truco['truco']}",
                    "back": truco.get("ejemplo", "Recuerda aplicar este truco"),
                })
        por_tema[t["id"]] = cards
    return json.dumps(por_tema, ensure_ascii=False)


# ── CSS ───────────────────────────────────────────────────────────────────────

def _css() -> str:
    return """<style>
:root{
  --bg:#f4f7fb;--card:#fff;--text:#152033;--muted:#64748b;--border:#dbe3ef;
  --primary:#2563eb;--primary-dark:#1e40af;--ok:#16a34a;--ok-bg:#dcfce7;
  --bad:#dc2626;--bad-bg:#fee2e2;--warn:#d97706;--warn-bg:#fef3c7;
  --purple:#7c3aed;--purple-bg:#f3e8ff;--shadow:0 16px 42px rgba(15,23,42,.08);
  --radius:20px;
}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{
  margin:0;
  font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  color:var(--text);
  background:radial-gradient(circle at 10% 0%,#dbeafe 0%,rgba(219,234,254,0) 34%),
             radial-gradient(circle at 90% 8%,#ccfbf1 0%,rgba(204,251,241,0) 34%),
             var(--bg);
  line-height:1.6;
}
header,main,.nav-inner{max-width:1220px;margin:0 auto}
header{padding:34px 20px 18px}
.hero{display:grid;grid-template-columns:1.4fr .6fr;gap:16px}
.hero-card,.stat-card,.panel,.card,.quiz-card,.module{
  background:rgba(255,255,255,.94);border:1px solid var(--border);
  border-radius:var(--radius);box-shadow:var(--shadow)
}
.hero-card{padding:32px}
.sf-badge{display:inline-block;background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;
  border-radius:999px;padding:5px 12px;font-size:.8rem;font-weight:800;margin-bottom:12px}
h1{font-size:clamp(1.8rem,3.5vw,3.2rem);line-height:1;letter-spacing:-.05em;margin:0 0 10px}
.subtitle{color:var(--muted);font-size:1rem;margin:0 0 14px}
.badges{display:flex;flex-wrap:wrap;gap:7px;margin-top:14px}
.badge{display:inline-flex;border-radius:999px;font-weight:800;align-items:center;
  padding:6px 11px;background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;font-size:.8rem}
.badge.source{background:#f3e8ff;color:#6d28d9;border-color:#ddd6fe}
.stat-grid{display:grid;gap:12px}
.stat-card{padding:18px}
.stat-number{font-size:2.2rem;font-weight:950;letter-spacing:-.05em}
.stat-label{color:var(--muted);font-size:.9rem;margin-top:4px}
nav{position:sticky;top:0;z-index:50;background:rgba(244,247,251,.92);
  backdrop-filter:blur(12px);border-bottom:1px solid var(--border)}
.nav-inner{padding:10px 20px;display:flex;gap:8px;overflow-x:auto;scrollbar-width:none}
.nav-inner::-webkit-scrollbar{display:none}
.nav-link,button{
  border:1px solid var(--border);background:#fff;color:var(--text);border-radius:999px;
  padding:8px 14px;font-weight:800;white-space:nowrap;cursor:pointer;font-size:.88rem;
  transition:all .15s ease;text-decoration:none;display:inline-flex;align-items:center
}
.nav-link:hover,button:hover{border-color:#93c5fd;background:#f0f7ff;transform:translateY(-1px)}
button.primary{background:var(--primary);color:#fff;border-color:var(--primary)}
button.primary:hover{background:var(--primary-dark)}
main{padding:24px 20px 70px}
section{margin:28px 0}
.section-title{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin:0 0 16px}
.section-title h2{margin:0;font-size:clamp(1.4rem,2.2vw,2rem);letter-spacing:-.04em}
.section-title p{margin:6px 0 0;color:var(--muted);max-width:800px}
.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.panel,.card,.quiz-card,.module{padding:20px}
.panel h3,.module h3{margin:0 0 12px;letter-spacing:-.025em}
.tema-num{display:inline-flex;align-items:center;justify-content:center;
  width:26px;height:26px;background:var(--primary);color:#fff;border-radius:8px;
  font-size:.8rem;font-weight:900;margin-right:10px;flex-shrink:0}
.tema-num-lg{display:inline-flex;align-items:center;justify-content:center;
  width:36px;height:36px;background:var(--primary);color:#fff;border-radius:10px;
  font-size:1rem;font-weight:900;margin-right:12px;flex-shrink:0;vertical-align:middle}
.tema-link{color:var(--text);text-decoration:none;display:flex;align-items:center}
.tema-link:hover{color:var(--primary)}
.pills{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.pill{display:inline-flex;border-radius:999px;font-weight:800;align-items:center;
  padding:4px 10px;font-size:.77rem;background:#eef2ff;color:#3730a3;border:1px solid #c7d2fe}
.resumen-texto p{margin:0 0 10px;color:var(--text)}
.resumen-texto p:last-child{margin-bottom:0}
.puntos-lista{margin:0;padding:0 0 0 18px}
.puntos-lista li{margin-bottom:8px;color:var(--text)}
.keywords-section,.trucos-section,.test-section{margin:14px 0}
.keywords-section h3,.trucos-section h3,.test-section h3{margin:0 0 12px;font-size:1.1rem;letter-spacing:-.02em}
.keywords-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}
.keyword-card{background:#fff;border:1px solid var(--border);border-radius:14px;padding:14px}
.keyword-card strong{color:var(--primary);display:block;margin-bottom:4px}
.keyword-card p{margin:0;color:var(--muted);font-size:.9rem}
.trucos-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px}
.truco{display:flex;gap:12px;background:#fffbeb;border:1px solid #fde68a;border-radius:14px;padding:14px}
.truco-icon{font-size:1.3rem;flex-shrink:0}
.truco strong{display:block;margin-bottom:4px}
.truco-ejemplo{margin:6px 0 0;color:var(--muted);font-size:.9rem}
.quiz-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px}
.quiz-card{padding:18px}
.quiz-card h3{margin:0 0 12px;font-size:.98rem;line-height:1.4;letter-spacing:-.01em}
.opciones{display:grid;gap:7px}
.quiz-option{border:1px solid var(--border);border-radius:12px;padding:10px 13px;
  background:#fff;cursor:pointer;font-size:.9rem;transition:all .15s ease;font-weight:600}
.quiz-option:hover{background:#f0f7ff;border-color:#93c5fd}
.quiz-option.correct{background:var(--ok-bg);border-color:#22c55e;color:#14532d}
.quiz-option.wrong{background:var(--bad-bg);border-color:#ef4444;color:#7f1d1d}
.quiz-note{margin-top:10px;font-size:.88rem;font-weight:700;border-radius:12px;
  padding:10px 12px;display:none}
.quiz-note.show{display:block}
.quiz-note.ok{background:var(--ok-bg);color:#14532d;border:1px solid #86efac}
.quiz-note.bad{background:var(--bad-bg);color:#7f1d1d;border:1px solid #fecaca}
.flashcards{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.flip{perspective:1000px;min-height:150px;cursor:pointer}
.flip-inner{position:relative;width:100%;min-height:150px;transform-style:preserve-3d;transition:transform .45s ease}
.flip.flipped .flip-inner{transform:rotateY(180deg)}
.flip-front,.flip-back{position:absolute;inset:0;border-radius:18px;border:1px solid var(--border);
  background:#fff;padding:16px;backface-visibility:hidden;box-shadow:var(--shadow);
  display:flex;flex-direction:column;justify-content:center}
.flip-back{transform:rotateY(180deg);background:#f0fdf4;border-color:#86efac}
.flip-front strong{font-size:1rem;color:var(--primary)}
.flip-front p{color:var(--muted);font-size:.85rem;margin:6px 0 0}
.flip-back p{color:#14532d;margin:0;font-size:.92rem}
.tabs{display:flex;flex-wrap:wrap;gap:8px}
.tab,.tab.active{border:1px solid var(--border);background:#fff;color:var(--text);
  border-radius:999px;padding:8px 14px;font-weight:800;cursor:pointer;font-size:.88rem;transition:all .15s ease}
.tab.active{background:var(--primary);color:#fff;border-color:var(--primary)}
.tab-content{display:none}.tab-content.active{display:block}
.exam-toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.exam-control{display:flex;align-items:center;gap:8px;font-weight:700}
.exam-control input{border:1px solid var(--border);border-radius:8px;padding:6px 8px;font-size:.9rem}
.toggle-label{display:flex;align-items:center;gap:6px;font-weight:700;cursor:pointer}
.score{margin-left:auto;background:#fff;border:1px solid var(--border);
  border-radius:999px;padding:8px 14px;font-weight:900;font-size:.9rem}
.result{border-radius:16px;padding:14px}
.result.good{background:var(--ok-bg);color:#14532d;border:1px solid #86efac}
.result.bad{background:var(--bad-bg);color:#7f1d1d;border:1px solid #fecaca}
.result.warn{background:var(--warn-bg);color:#78350f;border:1px solid #fcd34d}
table{width:100%;border-collapse:collapse;border:1px solid var(--border);border-radius:14px;overflow:hidden;background:#fff;margin-top:10px}
th,td{padding:10px 12px;border-bottom:1px solid var(--border);text-align:left}
th{background:#f8fafc;font-weight:800}
tr:last-child td{border-bottom:0}
@media(max-width:900px){
  .hero,.grid2,.grid3{grid-template-columns:1fr}
  .score{margin-left:0;width:100%;text-align:center}
}
@media print{nav,.exam-toolbar{display:none}body{background:white}}
</style>"""


# ── JavaScript ────────────────────────────────────────────────────────────────

def _script(preguntas_js: str, flashcards_js: str) -> str:
    return f"""<script>
// ── Datos generados ─────────────────────────────────────────────────────────
const PREGUNTAS = {preguntas_js};
const FLASHCARDS = {flashcards_js};

// ── Test por tema ────────────────────────────────────────────────────────────
function responder(qid, seleccionada, correcta, el, explicacion) {{
  const card = document.getElementById('card-' + qid);
  const note = document.getElementById('note-' + qid);
  // Marcar opciones
  card.querySelectorAll('.quiz-option').forEach((opt, i) => {{
    opt.style.pointerEvents = 'none';
    if (i === correcta) opt.classList.add('correct');
  }});
  if (seleccionada !== correcta) el.classList.add('wrong');
  // Mostrar explicación
  note.textContent = (seleccionada === correcta ? '✅ Correcto. ' : '❌ Incorrecto. ') + explicacion;
  note.className = 'quiz-note show ' + (seleccionada === correcta ? 'ok' : 'bad');
}}

// ── Flashcards ────────────────────────────────────────────────────────────────
function renderFlashcards(tid) {{
  const cards = FLASHCARDS[tid] || [];
  const grid = document.getElementById('fc-grid-' + tid);
  if (!grid) return;
  grid.innerHTML = cards.map((c, i) => `
    <div class="flip" id="flip-${{tid}}-${{i}}" onclick="this.classList.toggle('flipped')">
      <div class="flip-inner">
        <div class="flip-front">
          <strong>${{c.front}}</strong>
          <p>Haz clic para ver la definición</p>
        </div>
        <div class="flip-back">
          <p>${{c.back}}</p>
        </div>
      </div>
    </div>
  `).join('');
}}

function switchFlashTab(tid, btn) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('flash-' + tid).classList.add('active');
}}

// ── Modo examen ───────────────────────────────────────────────────────────────
let examPreguntas = [];
let examEstado = [];

function shuffleArray(arr) {{
  const out = [...arr];
  for (let i = out.length - 1; i > 0; i--) {{
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }}
  return out;
}}

function iniciarExamen() {{
  const count = Math.min(Number(document.getElementById('examCount').value) || 20, PREGUNTAS.length);
  const shuffle = document.getElementById('examShuffle').checked;
  const showTopic = document.getElementById('examShowTopic').checked;
  const pool = shuffle ? shuffleArray(PREGUNTAS) : [...PREGUNTAS];
  examPreguntas = pool.slice(0, count).map(q => ({{
    ...q,
    options: shuffleArray(q.options.map((op, i) => ({{ text: op, original: i }})))
      .map(o => o),
    _shuffle: true
  }}));
  // Re-mapear respuesta correcta tras mezclar opciones
  examPreguntas = pool.slice(0, count).map(q => {{
    const shuffled = shuffleArray(q.options.map((op, i) => ({{ text: op, idx: i }})));
    const newAnswer = shuffled.findIndex(o => o.idx === q.answer);
    return {{ ...q, options: shuffled.map(o => o.text), answer: newAnswer }};
  }});
  examEstado = new Array(examPreguntas.length).fill(null);
  renderExamen(showTopic);
  actualizarScore();
  document.getElementById('examBreakdown').style.display = 'none';
}}

function renderExamen(showTopic) {{
  const grid = document.getElementById('examGrid');
  grid.innerHTML = examPreguntas.map((q, idx) => `
    <div class="quiz-card" id="exam-card-${{idx}}">
      <h3>${{idx + 1}}. ${{q.q}}</h3>
      ${{showTopic ? `<div style="margin-bottom:8px"><span class="pill" style="background:var(--purple-bg);color:#6d28d9">${{q.topicName}}</span></div>` : ''}}
      <div class="opciones">
        ${{q.options.map((op, i) => `
          <div class="quiz-option" onclick="responderExamen(${{idx}}, ${{i}}, this)">
            ${{String.fromCharCode(97 + i)}}. ${{op}}
          </div>
        `).join('')}}
      </div>
      <div class="quiz-note" id="exam-note-${{idx}}"></div>
    </div>
  `).join('');
}}

function responderExamen(idx, sel, el) {{
  if (examEstado[idx] !== null) return;
  examEstado[idx] = sel;
  actualizarScore();
}}

function corregirExamen() {{
  if (!examPreguntas.length) iniciarExamen();
  let byTopic = {{}};
  examPreguntas.forEach((q, idx) => {{
    const card = document.getElementById('exam-card-' + idx);
    const note = document.getElementById('exam-note-' + idx);
    const selected = examEstado[idx];
    card.querySelectorAll('.quiz-option').forEach((op, i) => {{
      op.style.pointerEvents = 'none';
      if (i === q.answer) op.classList.add('correct');
    }});
    if (selected !== null && selected !== q.answer) {{
      card.querySelectorAll('.quiz-option')[selected].classList.add('wrong');
    }}
    const isCorrect = selected === q.answer;
    note.textContent = selected === null
      ? '⚠️ Sin responder. Correcta: ' + String.fromCharCode(97 + q.answer) + '. ' + q.why
      : (isCorrect ? '✅ Correcto. ' : '❌ Incorrecto. Correcta: ' + String.fromCharCode(97 + q.answer) + '. ') + q.why;
    note.className = 'quiz-note show ' + (isCorrect ? 'ok' : 'bad');
    if (!byTopic[q.topicName]) byTopic[q.topicName] = {{ total: 0, correct: 0 }};
    byTopic[q.topicName].total++;
    if (isCorrect) byTopic[q.topicName].correct++;
  }});
  const total = examPreguntas.length;
  const correct = examEstado.reduce((acc, val, idx) => acc + (val === examPreguntas[idx].answer ? 1 : 0), 0);
  const pct = Math.round((correct / total) * 100);
  document.getElementById('examScore').textContent = `Resultado: ${{correct}}/${{total}} · ${{pct}}%`;
  const rows = Object.entries(byTopic).map(([topic, v]) => {{
    const p = Math.round((v.correct / v.total) * 100);
    return `<tr><td>${{topic}}</td><td>${{v.correct}}/${{v.total}}</td><td>${{p}}%</td></tr>`;
  }}).join('');
  const box = document.getElementById('examBreakdown');
  box.style.display = 'block';
  box.className = 'result ' + (pct >= 85 ? 'good' : pct >= 65 ? 'warn' : 'bad');
  box.innerHTML = `<strong>Desglose por tema:</strong><table><tr><th>Tema</th><th>Aciertos</th><th>%</th></tr>${{rows}}</table>`;
}}

function resetExamen() {{
  document.getElementById('examGrid').innerHTML = '';
  document.getElementById('examScore').textContent = 'Sin iniciar';
  document.getElementById('examBreakdown').style.display = 'none';
  examPreguntas = [];
  examEstado = [];
}}

function actualizarScore() {{
  if (!examPreguntas.length) return;
  const respondidas = examEstado.filter(x => x !== null).length;
  const correctas = examEstado.reduce((acc, val, idx) => acc + (val === examPreguntas[idx]?.answer ? 1 : 0), 0);
  document.getElementById('examScore').textContent =
    `${{correctas}}/${{respondidas}} correctas · ${{respondidas}}/${{examPreguntas.length}} respondidas`;
}}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {{
  Object.keys(FLASHCARDS).forEach(tid => renderFlashcards(tid));
}});
</script>"""
