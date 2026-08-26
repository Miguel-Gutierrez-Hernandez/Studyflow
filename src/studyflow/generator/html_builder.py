import html
import json
import re
from datetime import datetime


def _e(value) -> str:
    """HTML-escape any LLM/user-derived text before interpolating it."""
    return html.escape(str(value), quote=True)


def _js_str(value) -> str:
    """Escape text for safe interpolation inside a single-quoted JS string
    (used only for small inline handlers; bulk data goes through json.dumps)."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace('"', '\\"')
        .replace("\n", " ")
    )


def build_html(material: dict) -> str:
    title = material["title"]
    topics = material["topics"]
    sources = material.get("sources", [])
    stats = material.get("stats", {})
    date = datetime.now().strftime("%Y-%m-%d")

    all_questions_js = _serialize_questions(topics)
    storage_ns = _storage_namespace(title, date)

    sections = "\n".join(_section_topic(t, i) for i, t in enumerate(topics))

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{_e(title)} — StudyFlow AI</title>
{_css()}
</head>
<body>

<a class="skip-link" href="#main-content">Saltar al contenido</a>

<header>
  <div class="hero">
    <div class="hero-card">
      <div class="sf-badge">⚡ StudyFlow AI</div>
      <h1>{_e(title)}</h1>
      <p class="subtitle">Material generado automáticamente · {date}</p>
      <div class="badges">
        {"".join(f'<span class="badge">{_e(t["title"])}</span>' for t in topics)}
        {"".join(f'<span class="badge source">📄 {_e(s)}</span>' for s in sources)}
      </div>
    </div>
    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-number">{stats.get("n_topics", len(topics))}</div>
        <div class="stat-label">temas</div>
      </div>
      <div class="stat-card">
        <div class="stat-number">{stats.get("n_questions", 0)}</div>
        <div class="stat-label">preguntas test</div>
      </div>
      <div class="stat-card progress-card">
        <div class="stat-number" id="progressCount">0/{len(topics)}</div>
        <div class="stat-label">temas dominados</div>
      </div>
    </div>
  </div>
</header>

<nav>
  <div class="nav-inner">
    <a class="nav-link" href="#overview">📋 Índice</a>
    {"".join(f'<a class="nav-link" href="#{_e(t["id"])}">{_e(t["title"])}</a>' for t in topics)}
    <a class="nav-link" href="#exam">🎓 Simulacro</a>
    <button class="nav-link toggle-btn" id="darkModeBtn" type="button"
      aria-pressed="false" title="Alternar modo oscuro">🌙 Oscuro</button>
  </div>
</nav>

<main id="main-content">
  {_section_overview(topics)}
  {sections}
  {_section_exam()}
</main>

{_script(all_questions_js, storage_ns, topics)}
</body>
</html>"""


def _storage_namespace(title: str, date: str) -> str:
    """A stable-ish key prefix for localStorage so progress from one
    generated document doesn't collide with another opened in the same browser."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
    return f"sf_{slug}_{date}"


# ── Overview ──────────────────────────────────────────────────────────────────

def _section_overview(topics: list[dict]) -> str:
    items = "".join(
        f"""<div class="module" id="overview-{_e(t['id'])}" data-topic-id="{_e(t['id'])}">
          <h3><a href="#{_e(t['id'])}" class="topic-link">
            <span class="topic-num">{i+1}</span>{_e(t['title'])}
            <span class="topic-check" aria-hidden="true"></span>
          </a></h3>
          <div class="pills">
            {"".join(f'<span class="pill">{_e(s["title"])}</span>' for s in t.get("subtopics", []))}
          </div>
        </div>"""
        for i, t in enumerate(topics)
    )
    return f"""<section id="overview">
  <div class="section-title">
    <div><h2>📋 Índice de contenidos</h2>
    <p>Visión general. Haz clic en un tema para ir directamente. El check aparece cuando superas el 70% en ese tema dentro del simulacro global.</p></div>
  </div>
  <!-- Cambiado grid3 por overview-list para forzar filas en lugar de columnas -->
  <div class="overview-list">{items}</div>
</section>"""


# ── Topic section ─────────────────────────────────────────────────────────────

def _section_topic(topic: dict, idx: int) -> str:
    tid = topic["id"]
    title = topic["title"]
    subtopics = topic.get("subtopics", [])
    flashcards = topic.get("flashcards", [])

    subtopic_tabs = _subtopic_list(tid, subtopics)
    flashcards_html = _flashcards_grid(tid, flashcards)

    return f"""<section id="{_e(tid)}">
  <div class="section-title">
    <div>
      <h2><span class="topic-num-lg">{idx+1}</span>{_e(title)}</h2>
      <p>{"  ·  ".join(_e(s["title"]) for s in subtopics)}</p>
    </div>
  </div>

  {subtopic_tabs}

  <div class="subsection">
    <div class="section-title"><div>
      <h3>🃏 Flashcards — {_e(title)}</h3>
      <p>Haz clic o pulsa Enter en cada tarjeta para ver la definición. Marca las que ya sabes.</p>
    </div>
    <label class="toggle-label">
      <input type="checkbox" class="review-filter" data-topic="{_e(tid)}"> Solo para repasar
    </label>
    </div>
    {flashcards_html}
  </div>

</section>"""


# ── Subtopics (sequential, non-tabbed) ──────────────────────────────────────

def _subtopic_list(tid: str, subtopics: list[dict]) -> str:
    if not subtopics:
        return ""
    items = "".join(
        f'<div class="subtopic-item" id="{_e(tid)}__{_e(sub["id"])}">'
        f'<h3>{i+1}. {_e(sub["title"])}</h3>'
        f'{_subtopic_content(sub)}'
        f'</div>'
        for i, sub in enumerate(subtopics)
    )
    return f'<div class="subtopic-block">{items}</div>'


def _subtopic_content(sub: dict) -> str:
    explanation = (sub.get("explanation") or "").strip()
    concepts = sub.get("concepts", [])

    concepts_rows = "".join(
        f"<tr><td><strong>{_e(c.get('concept',''))}</strong></td><td>{_e(c.get('definition',''))}</td></tr>"
        for c in concepts
    )

    concepts_table = f"""<div class="panel" style="margin-top:14px">
      <h4>🔑 Conceptos clave</h4>
      <table>
        <tr><th scope="col">Concepto</th><th scope="col">Definición</th></tr>
        {concepts_rows}
      </table>
    </div>""" if concepts_rows else ""

    if not explanation and not concepts_rows:
        return """<div class="panel muted-panel">
      <p class="muted-note">⚠️ No se pudo generar contenido para este subtema (el modelo no devolvió una
      respuesta válida). Prueba a regenerar este proyecto con un modelo más grande, o revisa el documento
      fuente para este apartado.</p>
    </div>"""

    explanation_panel = f"""<div class="panel explanation-panel">
    <div class="explanation-text">{_paragraphs(explanation)}</div>
  </div>""" if explanation else ""

    return f"""<div class="subtopic-content">
  {explanation_panel}
  {concepts_table}
</div>"""


# ── Flashcards ────────────────────────────────────────────────────────────────

def _flashcards_grid(tid: str, flashcards: list[dict]) -> str:
    if not flashcards:
        return "<p class='muted-note'>No se generaron flashcards para este tema.</p>"
    cards = ""
    for i, fc in enumerate(flashcards):
        fid = f"{tid}__fc{i}"
        cards += f"""<div class="flip" id="flip-{_e(fid)}" data-fcid="{_e(fid)}" data-topic="{_e(tid)}"
          role="button" tabindex="0" aria-pressed="false"
          aria-label="Flashcard: {_e(fc.get('front',''))}. Pulsa Enter para ver la respuesta."
          onclick="flipCard('{_js_str(fid)}')" onkeydown="if(event.key==='Enter'||event.key===' '){{event.preventDefault();flipCard('{_js_str(fid)}');}}">
          <div class="flip-inner">
            <div class="flip-front">
              <strong>{_e(fc.get('front',''))}</strong>
              <p>Haz clic o Enter para ver</p>
            </div>
            <div class="flip-back">
              <p>{_e(fc.get('back',''))}</p>
              <div class="flip-actions" onclick="event.stopPropagation()">
                <button type="button" class="know-btn" data-fcid="{_e(fid)}" data-state="know" onclick="markCard(event,'{_js_str(fid)}','know')">✓ Lo sé</button>
                <button type="button" class="know-btn" data-fcid="{_e(fid)}" data-state="review" onclick="markCard(event,'{_js_str(fid)}','review')">↻ Repasar</button>
              </div>
            </div>
          </div>
        </div>"""
    return f'<div class="flashcards" data-topic="{_e(tid)}">{cards}</div>'


# ── Global exam ───────────────────────────────────────────────────────────────

def _section_exam() -> str:
    return """<section id="exam">
  <div class="section-title">
    <div><h2>🎓 Simulacro global</h2>
    <p>Preguntas mezcladas de todos los temas. Configura y empieza cuando estés listo.</p></div>
  </div>
  <div class="panel" style="margin-bottom:14px">
    <div class="exam-toolbar">
      <div class="exam-control">
        <label for="examCount">Preguntas</label>
        <input type="number" id="examCount" value="20" min="5" max="200" style="width:80px">
      </div>
      <label class="toggle-label"><input type="checkbox" id="examShuffle" checked> Mezclar</label>
      <label class="toggle-label"><input type="checkbox" id="examShowTopic"> Mostrar tema</label>
      <button class="primary" type="button" onclick="startExam()">▶ Iniciar</button>
      <button type="button" onclick="gradeExam()">✅ Corregir</button>
      <button type="button" onclick="resetExam()">🔄 Reiniciar</button>
      <div class="score" id="examScore" role="status">Sin iniciar</div>
    </div>
  </div>
  <div id="examGrid" class="quiz-grid"></div>
  <div id="examBreakdown" class="result" style="display:none;margin-top:14px"></div>
  <div id="examHistory" class="panel" style="margin-top:14px;display:none">
    <h4>📈 Historial de simulacros</h4>
    <table id="examHistoryTable"><tr><th scope="col">Fecha</th><th scope="col">Resultado</th><th scope="col">%</th></tr></table>
  </div>
</section>"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _paragraphs(text: str) -> str:
    escaped = _e(text)
    parts = [p.strip() for p in escaped.split("\n\n") if p.strip()]
    return "".join(f"<p>{p}</p>" for p in parts) if parts else f"<p>{escaped}</p>"


def _serialize_questions(topics: list[dict]) -> str:
    all_q = []
    for t in topics:
        for q in t.get("questions", []):
            all_q.append({
                "topicId": t["id"],
                "topicName": t["title"],
                "q": q["question"],
                "options": q["options"],
                "answer": q["correct"],
                "why": q.get("explanation", ""),
            })
    return json.dumps(all_q, ensure_ascii=False)


# ── CSS ───────────────────────────────────────────────────────────────────────

def _css() -> str:
    return """<style>
:root{
  --bg:#f4f7fb;--card:#fff;--text:#152033;--muted:#64748b;--border:#dbe3ef;
  --primary:#2563eb;--primary-dark:#1e40af;--ok:#16a34a;--ok-bg:#dcfce7;
  --bad:#dc2626;--bad-bg:#fee2e2;--warn:#d97706;--warn-bg:#fef3c7;
  --purple:#7c3aed;--purple-bg:#f3e8ff;--cyan-bg:#ecfeff;--cyan:#0e7490;
  --shadow:0 16px 42px rgba(15,23,42,.08);--radius:24px;
}
html[data-theme="dark"]{
  --bg:#0f1420;--card:#1a2233;--text:#e6ebf5;--muted:#93a0bd;--border:#2c3650;
  --primary:#5b8def;--primary-dark:#7ea6f5;--ok:#22c55e;--ok-bg:#14301f;
  --bad:#f87171;--bad-bg:#3a1717;--warn:#fbbf24;--warn-bg:#3a2c0d;
  --purple:#a78bfa;--purple-bg:#2a2044;--cyan-bg:#0d2b30;--cyan:#5eead4;
  --shadow:0 16px 42px rgba(0,0,0,.45);
}
*{box-sizing:border-box}html{scroll-behavior:smooth}
.skip-link{position:absolute;left:-999px;top:0;background:var(--primary);color:#fff;
  padding:10px 16px;border-radius:0 0 10px 0;z-index:999;font-weight:800}
.skip-link:focus{left:0}
body{
  margin:0;
  font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  color:var(--text);
  background:radial-gradient(circle at 10% 0%,#dbeafe 0%,rgba(219,234,254,0) 34%),
             radial-gradient(circle at 90% 8%,#ccfbf1 0%,rgba(204,251,241,0) 34%),
             var(--bg);
  line-height:1.55;
  transition:background-color .2s ease,color .2s ease
}
html[data-theme="dark"] body{
  background:radial-gradient(circle at 10% 0%,#1b2a4a 0%,rgba(27,42,74,0) 34%),
             radial-gradient(circle at 90% 8%,#0d3b3a 0%,rgba(13,59,58,0) 34%),
             var(--bg)
}
header,main,.nav-inner{max-width:1220px;margin:0 auto}
header{padding:34px 20px 18px}
.hero{display:grid;grid-template-columns:1.35fr .65fr;gap:16px}
.hero-card,.stat-card,.panel,.card,.quiz-card,.module{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--radius);box-shadow:var(--shadow)
}
.hero-card{padding:30px}
.sf-badge{display:inline-block;background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;
  border-radius:999px;padding:5px 12px;font-size:.8rem;font-weight:800;margin-bottom:12px}
html[data-theme="dark"] .sf-badge{background:#1e2a4a;color:#93b4fb;border-color:#2c3d63}
h1{font-size:clamp(2rem,4vw,4rem);line-height:.96;letter-spacing:-.065em;margin:0 0 12px}
h3,h4{letter-spacing:-.025em;margin:0 0 10px}
h4{font-size:1rem;color:var(--text)}
.subtitle{color:var(--muted);font-size:1.05rem;margin:0 0 14px}
.badges{display:flex;flex-wrap:wrap;gap:7px;margin-top:14px}
.badge{display:inline-flex;border-radius:999px;font-weight:900;align-items:center;
  padding:6px 11px;background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;font-size:.82rem}
html[data-theme="dark"] .badge{background:#1e2a4a;color:#93b4fb;border-color:#2c3d63}
.badge.source{background:#f3e8ff;color:#6d28d9;border-color:#ddd6fe}
html[data-theme="dark"] .badge.source{background:#241a3d;color:#c4a9f7;border-color:#382a5c}
.stat-grid{display:grid;gap:12px}
.stat-card{padding:18px}
.stat-number{font-size:2.1rem;font-weight:950;letter-spacing:-.05em}
.stat-label{color:var(--muted);font-size:.93rem}
.progress-card .stat-number{color:var(--ok)}
nav{position:sticky;top:0;z-index:50;background:rgba(244,247,251,.91);
  backdrop-filter:blur(12px);border-top:1px solid rgba(255,255,255,.55);
  border-bottom:1px solid var(--border)}
html[data-theme="dark"] nav{background:rgba(15,20,32,.88);border-top-color:rgba(255,255,255,.06)}
.nav-inner{padding:11px 20px;display:flex;gap:9px;overflow-x:auto;scrollbar-width:none}
.nav-inner::-webkit-scrollbar{display:none}
.nav-link,button{
  border:1px solid var(--border);background:var(--card);color:var(--text);border-radius:999px;
  padding:9px 13px;font-weight:850;white-space:nowrap;cursor:pointer;font-size:.9rem;
  transition:transform .12s ease,border .18s ease,background .18s ease;
  text-decoration:none;display:inline-flex;align-items:center;font-family:inherit
}
.nav-link:hover,button:hover{transform:translateY(-1px);border-color:#93c5fd;background:#f8fbff}
html[data-theme="dark"] .nav-link:hover,html[data-theme="dark"] button:hover{background:#22304d;border-color:#3d5a80}
button.primary{background:var(--primary);color:#fff;border-color:var(--primary)}
button.primary:hover{background:var(--primary-dark)}
.toggle-btn{margin-left:auto}
.toggle-btn[aria-pressed="true"]{background:var(--primary);color:#fff;border-color:var(--primary)}
:focus-visible{outline:3px solid var(--primary);outline-offset:2px}
main{padding:24px 20px 70px}
section{margin:32px 0;padding-top:8px}
.subsection{margin-top:24px}
.section-title{display:flex;justify-content:space-between;align-items:end;gap:16px;margin:0 0 14px;flex-wrap:wrap}
.section-title h2{margin:0;font-size:clamp(1.45rem,2.3vw,2.25rem);letter-spacing:-.045em;line-height:1.05}
.section-title h3{margin:0;font-size:1.25rem}
.section-title p{margin:6px 0 0;color:var(--muted);max-width:850px}
.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.overview-list{display:flex;flex-direction:column;gap:14px}
.panel,.card,.quiz-card,.module{padding:18px}
.muted-note{color:var(--muted)}
.topic-num{display:inline-flex;align-items:center;justify-content:center;
  width:26px;height:26px;background:var(--primary);color:#fff;border-radius:8px;
  font-size:.8rem;font-weight:900;margin-right:10px;flex-shrink:0}
.topic-num-lg{display:inline-flex;align-items:center;justify-content:center;
  width:38px;height:38px;background:var(--primary);color:#fff;border-radius:12px;
  font-size:1.05rem;font-weight:900;margin-right:12px;flex-shrink:0;vertical-align:middle}
.topic-link{color:var(--text);text-decoration:none;display:flex;align-items:center}
.topic-link:hover{color:var(--primary)}
.topic-check{margin-left:8px;color:var(--ok);font-weight:900}
.topic-check.done::after{content:"✓ dominado"}
.pills{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.pill{display:inline-flex;border-radius:999px;font-weight:800;align-items:center;
  padding:4px 10px;font-size:.77rem;background:#eef2ff;color:#3730a3;border:1px solid #c7d2fe}
html[data-theme="dark"] .pill{background:#1e2144;color:#a5b4fc;border-color:#312e70}
/* Subtopics (sequential) */
.subtopic-block{display:grid;gap:22px;margin-bottom:10px}
.subtopic-item{border-top:1px solid var(--border);padding-top:18px}
.subtopic-item:first-child{border-top:none;padding-top:0}
.subtopic-item h3{font-size:1.1rem;color:var(--primary);margin-bottom:12px}
.subtopic-content{display:grid;gap:14px}
.explanation-panel{border-left:4px solid var(--primary)}
.explanation-text p{margin:0 0 10px;color:var(--text);line-height:1.65}
.explanation-text p:last-child{margin-bottom:0}
.muted-panel{border-left:4px solid var(--warn);background:var(--warn-bg)}
.muted-panel .muted-note{color:inherit;margin:0}
/* Tables */
table{width:100%;border-collapse:collapse;border:1px solid var(--border);
  border-radius:18px;overflow:hidden;background:var(--card)}
th,td{padding:11px 13px;border-bottom:1px solid var(--border);text-align:left;vertical-align:top}
th{background:rgba(0,0,0,.02);font-weight:800}
html[data-theme="dark"] th{background:rgba(255,255,255,.03)}
tr:last-child td{border-bottom:0}
/* Quiz */
.quiz-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px}
.quiz-card{padding:18px}
.quiz-card h3{margin:0 0 12px;font-size:.97rem;line-height:1.4;letter-spacing:-.01em}
.opciones{display:grid;gap:7px}
.quiz-option{border:1px solid var(--border);border-radius:12px;padding:10px 13px;
  background:var(--card);cursor:pointer;font-size:.9rem;transition:all .15s ease;font-weight:600;
  text-align:left;width:100%;color:var(--text)}
.quiz-option:hover{background:#f0f7ff;border-color:#93c5fd}
html[data-theme="dark"] .quiz-option:hover{background:#1c2b4a}
.quiz-option.correct{background:var(--ok-bg);border-color:#22c55e;color:#14532d}
html[data-theme="dark"] .quiz-option.correct{color:#86efac}
.quiz-option.wrong{background:var(--bad-bg);border-color:#ef4444;color:#7f1d1d}
html[data-theme="dark"] .quiz-option.wrong{color:#fca5a5}
.quiz-option:disabled{cursor:default}
.quiz-note{margin-top:10px;font-size:.88rem;font-weight:700;border-radius:12px;
  padding:10px 12px;display:none}
.quiz-note.show{display:block}
.quiz-note.ok{background:var(--ok-bg);color:#14532d;border:1px solid #86efac}
.quiz-note.bad{background:var(--bad-bg);color:#7f1d1d;border:1px solid #fecaca}
html[data-theme="dark"] .quiz-note.ok{color:#86efac}
html[data-theme="dark"] .quiz-note.bad{color:#fca5a5}
.retry-btn{margin-top:10px;font-size:.8rem;padding:6px 12px;display:none}
/* Flashcards */
.flashcards{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.flip{perspective:1000px;min-height:180px;cursor:pointer}
.flip-inner{position:relative;width:100%;min-height:180px;transform-style:preserve-3d;
  transition:transform .45s ease}
.flip.flipped .flip-inner{transform:rotateY(180deg)}
.flip-front,.flip-back{position:absolute;inset:0;border-radius:20px;border:1px solid var(--border);
  background:var(--card);padding:18px;backface-visibility:hidden;box-shadow:var(--shadow);
  display:flex;flex-direction:column;justify-content:center}
.flip-back{transform:rotateY(180deg);background:var(--ok-bg);border-color:#86efac}
.flip-front strong{font-size:1rem;color:var(--primary);display:block;margin-bottom:6px}
.flip-front p{color:var(--muted);font-size:.85rem;margin:0}
.flip-back p{color:#14532d;margin:0 0 10px;font-size:.92rem;line-height:1.5}
html[data-theme="dark"] .flip-back p{color:#bbf7d0}
.flip-actions{display:flex;gap:6px}
.know-btn{font-size:.72rem;padding:5px 9px;border-radius:8px}
.know-btn[data-state="know"].active{background:var(--ok);color:#fff;border-color:var(--ok)}
.know-btn[data-state="review"].active{background:var(--warn);color:#fff;border-color:var(--warn)}
.flip.card-known{opacity:.55}
.flip.card-review .flip-front{border-color:var(--warn);border-width:2px}
.flip.filtered-out{display:none}
/* Exam */
.exam-toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.exam-control{display:flex;align-items:center;gap:8px;font-weight:700}
.exam-control input{border:1px solid var(--border);border-radius:8px;padding:6px 8px;font-size:.9rem;
  background:var(--card);color:var(--text)}
.toggle-label{display:flex;align-items:center;gap:6px;font-weight:700;cursor:pointer}
.score{margin-left:auto;background:var(--card);border:1px solid var(--border);
  border-radius:999px;padding:8px 14px;font-weight:900;font-size:.9rem}
.result{border-radius:16px;padding:14px}
.result.good{background:var(--ok-bg);color:#14532d;border:1px solid #86efac}
.result.bad{background:var(--bad-bg);color:#7f1d1d;border:1px solid #fecaca}
.result.warn{background:var(--warn-bg);color:#78350f;border:1px solid #fcd34d}
html[data-theme="dark"] .result.good{color:#86efac}
html[data-theme="dark"] .result.bad{color:#fca5a5}
html[data-theme="dark"] .result.warn{color:#fbbf24}
@media(max-width:900px){
  .hero,.grid2,.overview-list{grid-template-columns:1fr}
  .score{margin-left:0;width:100%;text-align:center}
  .section-title{display:block}
}
@media print{
  nav,.exam-toolbar,.toggle-btn,.retry-btn,.flip-actions,.skip-link{display:none !important}
  body{background:white;color:#000}
  .subtopic-item{page-break-inside:avoid;margin-bottom:16px}
  .panel,.quiz-card,.module,table,.flip{page-break-inside:avoid}
  .flip{perspective:none;min-height:auto}
  .flip-inner{position:static;transform:none !important;display:block}
  .flip-front,.flip-back{position:static;transform:none !important;box-shadow:none;
    border-radius:8px;margin-bottom:6px}
  .flip-back{background:#f0fdf4}
  .quiz-option{border:1px solid #ccc}
}
</style>"""


# ── JavaScript ────────────────────────────────────────────────────────────────

def _script(questions_js: str, storage_ns: str, topics: list[dict]) -> str:
    topic_ids_js = json.dumps([t["id"] for t in topics], ensure_ascii=False)
    return f"""<script>
const QUESTIONS = {questions_js};
const TOPIC_IDS = {topic_ids_js};
const NS = '{storage_ns}';

// -- localStorage helpers ---------------------------------------------------
function lsGet(key, fallback) {{
  try {{
    const v = localStorage.getItem(NS + '_' + key);
    return v === null ? fallback : JSON.parse(v);
  }} catch (e) {{ return fallback; }}
}}
function lsSet(key, value) {{
  try {{ localStorage.setItem(NS + '_' + key, JSON.stringify(value)); }} catch (e) {{ /* storage unavailable */ }}
}}

// -- Dark mode ----------------------------------------------------------------
function applyTheme(dark) {{
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  document.getElementById('darkModeBtn').setAttribute('aria-pressed', dark ? 'true' : 'false');
  document.getElementById('darkModeBtn').textContent = dark ? '☀️ Claro' : '🌙 Oscuro';
}}
function initTheme() {{
  const stored = lsGet('theme', null);
  const dark = stored !== null ? stored : window.matchMedia('(prefers-color-scheme: dark)').matches;
  applyTheme(dark);
}}
document.getElementById('darkModeBtn').addEventListener('click', () => {{
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  applyTheme(!isDark);
  lsSet('theme', !isDark);
}});
initTheme();

// -- Flashcards: flip, know/review marking, filter, persistence --------------
function flipCard(fcid) {{
  const el = document.getElementById('flip-' + fcid);
  const flipped = el.classList.toggle('flipped');
  el.setAttribute('aria-pressed', flipped ? 'true' : 'false');
}}

function markCard(evt, fcid, state) {{
  evt.stopPropagation();
  const el = document.getElementById('flip-' + fcid);
  const current = lsGet('flash_' + fcid, null);
  const next = current === state ? null : state; // click again to unmark
  lsSet('flash_' + fcid, next);
  applyCardState(el, next);
}}

function applyCardState(el, state) {{
  el.classList.remove('card-known', 'card-review');
  el.querySelectorAll('.know-btn').forEach(b => b.classList.remove('active'));
  if (state === 'know') {{
    el.classList.add('card-known');
    el.querySelector('.know-btn[data-state="know"]').classList.add('active');
  }} else if (state === 'review') {{
    el.classList.add('card-review');
    el.querySelector('.know-btn[data-state="review"]').classList.add('active');
  }}
}}

function restoreFlashcardState() {{
  document.querySelectorAll('.flip').forEach(el => {{
    const state = lsGet('flash_' + el.dataset.fcid, null);
    applyCardState(el, state);
  }});
}}

document.querySelectorAll('.review-filter').forEach(cb => {{
  cb.addEventListener('change', () => {{
    const topic = cb.dataset.topic;
    const onlyReview = cb.checked;
    document.querySelectorAll(`.flashcards[data-topic="${{topic}}"] .flip`).forEach(el => {{
      const isReview = el.classList.contains('card-review');
      const notMarkedKnow = !el.classList.contains('card-known');
      el.classList.toggle('filtered-out', onlyReview && !(isReview || notMarkedKnow && !isReview && false) && !isReview);
    }});
  }});
}});

// -- Topic progress (overview checkmarks + header counter) --------------------
// A topic counts as "dominado" once you've scored 70%+ on it within a graded
// global exam (there's no more per-topic quiz to track individually).
const MASTERY_THRESHOLD = 70;

function topicIsDone(topicId) {{
  return !!lsGet('examtopic_' + topicId, false);
}}

function updateTopicProgress(topicId) {{
  const done = topicIsDone(topicId);
  const marker = document.querySelector(`#overview-${{topicId}} .topic-check`);
  if (marker) marker.classList.toggle('done', done);
  const doneCount = TOPIC_IDS.filter(topicIsDone).length;
  const counter = document.getElementById('progressCount');
  if (counter) counter.textContent = doneCount + '/' + TOPIC_IDS.length;
}}

function initProgress() {{
  TOPIC_IDS.forEach(updateTopicProgress);
}}

// -- Global exam ----------------------------------------------------------------
let examQ = [], examState = [];

function shuffle(arr) {{
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {{
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }}
  return a;
}}

function startExam() {{
  const count = Math.min(Number(document.getElementById('examCount').value) || 20, QUESTIONS.length);
  const doShuffle = document.getElementById('examShuffle').checked;
  const showTopic = document.getElementById('examShowTopic').checked;
  const pool = doShuffle ? shuffle(QUESTIONS) : [...QUESTIONS];
  examQ = pool.slice(0, count).map(q => {{
    const opts = shuffle(q.options.map((op, i) => ({{text: op, idx: i}})));
    return {{ ...q, options: opts.map(o => o.text), answer: opts.findIndex(o => o.idx === q.answer) }};
  }});
  examState = new Array(examQ.length).fill(null);
  document.getElementById('examGrid').innerHTML = examQ.map((q, idx) => `
    <div class="quiz-card" id="exam-card-${{idx}}">
      <h3>${{idx + 1}}. ${{escapeHtml(q.q)}}</h3>
      ${{showTopic ? `<div style="margin-bottom:8px"><span class="pill" style="background:var(--purple-bg);color:var(--purple)">${{escapeHtml(q.topicName)}}</span></div>` : ''}}
      <div class="opciones">
        ${{q.options.map((op, i) => `
          <button type="button" class="quiz-option" onclick="answerExam(${{idx}},${{i}},this)">${{String.fromCharCode(97+i)}}. ${{escapeHtml(op)}}</button>
        `).join('')}}
      </div>
      <div class="quiz-note" id="exam-note-${{idx}}" role="status"></div>
    </div>
  `).join('');
  updateScore();
  document.getElementById('examBreakdown').style.display = 'none';
}}

function escapeHtml(s) {{
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}}

function answerExam(idx, sel) {{
  if (examState[idx] !== null) return;
  examState[idx] = sel;
  updateScore();
}}

function gradeExam() {{
  if (!examQ.length) startExam();
  const byTopic = {{}};
  examQ.forEach((q, idx) => {{
    const card = document.getElementById('exam-card-' + idx);
    const note = document.getElementById('exam-note-' + idx);
    const sel = examState[idx];
    card.querySelectorAll('.quiz-option').forEach((op, i) => {{
      op.disabled = true;
      if (i === q.answer) op.classList.add('correct');
    }});
    if (sel !== null && sel !== q.answer) card.querySelectorAll('.quiz-option')[sel].classList.add('wrong');
    const ok = sel === q.answer;
    note.textContent = sel === null
      ? '⚠️ Sin responder. Correcta: ' + String.fromCharCode(97 + q.answer) + '. ' + q.why
      : (ok ? '✅ Correcto. ' : '❌ Incorrecto. Correcta: ' + String.fromCharCode(97 + q.answer) + '. ') + q.why;
    note.className = 'quiz-note show ' + (ok ? 'ok' : 'bad');
    if (!byTopic[q.topicId]) byTopic[q.topicId] = {{name: q.topicName, total:0, correct:0}};
    byTopic[q.topicId].total++;
    if (ok) byTopic[q.topicId].correct++;
  }});
  const total = examQ.length;
  const correct = examState.reduce((acc, val, idx) => acc + (val === examQ[idx].answer ? 1 : 0), 0);
  const pct = Math.round((correct / total) * 100);
  document.getElementById('examScore').textContent = `Resultado: ${{correct}}/${{total}} · ${{pct}}%`;
  const rows = Object.values(byTopic).map(v => {{
    const p = Math.round((v.correct/v.total)*100);
    return `<tr><td>${{escapeHtml(v.name)}}</td><td>${{v.correct}}/${{v.total}}</td><td>${{p}}%</td></tr>`;
  }}).join('');
  const box = document.getElementById('examBreakdown');
  box.style.display = 'block';
  box.className = 'result ' + (pct >= 85 ? 'good' : pct >= 65 ? 'warn' : 'bad');
  box.innerHTML = `<strong>Desglose por tema:</strong><table><tr><th scope="col">Tema</th><th scope="col">Aciertos</th><th scope="col">%</th></tr>${{rows}}</table>`;

  // Mark each topic touched by this exam as mastered (or not) based on this attempt.
  Object.entries(byTopic).forEach(([topicId, v]) => {{
    const topicPct = Math.round((v.correct / v.total) * 100);
    lsSet('examtopic_' + topicId, topicPct >= MASTERY_THRESHOLD);
    updateTopicProgress(topicId);
  }});

  const history = lsGet('exam_history', []);
  history.push({{ date: new Date().toLocaleString('es'), correct, total, pct }});
  lsSet('exam_history', history.slice(-20));
  renderExamHistory();
}}

function renderExamHistory() {{
  const history = lsGet('exam_history', []);
  const panel = document.getElementById('examHistory');
  if (!history.length) {{ panel.style.display = 'none'; return; }}
  panel.style.display = 'block';
  const rows = history.slice().reverse().map(h =>
    `<tr><td>${{h.date}}</td><td>${{h.correct}}/${{h.total}}</td><td>${{h.pct}}%</td></tr>`
  ).join('');
  document.getElementById('examHistoryTable').innerHTML =
    '<tr><th scope="col">Fecha</th><th scope="col">Resultado</th><th scope="col">%</th></tr>' + rows;
}}

function resetExam() {{
  document.getElementById('examGrid').innerHTML = '';
  document.getElementById('examScore').textContent = 'Sin iniciar';
  document.getElementById('examBreakdown').style.display = 'none';
  examQ = []; examState = [];
}}

function updateScore() {{
  if (!examQ.length) return;
  const answered = examState.filter(x => x !== null).length;
  const correct = examState.reduce((acc, val, idx) => acc + (val === examQ[idx]?.answer ? 1 : 0), 0);
  document.getElementById('examScore').textContent =
    `${{correct}}/${{answered}} correctas · ${{answered}}/${{examQ.length}} respondidas`;
}}

// -- Init ------------------------------------------------------------------------
restoreFlashcardState();
renderExamHistory();
initProgress();
</script>"""