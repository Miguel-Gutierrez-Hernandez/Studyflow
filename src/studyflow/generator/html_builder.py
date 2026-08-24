"""
generador/html_builder.py — Builds the final study HTML.

Structure per topic (matching reference guide style):
  - Tabs per subtopic, each with: explanation, concepts table, confusions table
  - Sister questions table
  - Flashcards grid
  - Quiz with immediate feedback
"""

import json
from datetime import datetime


def build_html(material: dict) -> str:
    title = material["title"]
    topics = material["topics"]
    sources = material.get("sources", [])
    stats = material.get("stats", {})
    date = datetime.now().strftime("%Y-%m-%d")

    all_questions_js = _serialize_questions(topics)

    sections = "\n".join(_section_topic(t, i) for i, t in enumerate(topics))

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{title} — StudyFlow AI</title>
{_css()}
</head>
<body>

<header>
  <div class="hero">
    <div class="hero-card">
      <div class="sf-badge">⚡ StudyFlow AI</div>
      <h1>{title}</h1>
      <p class="subtitle">Material generado automáticamente · {date}</p>
      <div class="badges">
        {"".join(f'<span class="badge">{t["title"]}</span>' for t in topics)}
        {"".join(f'<span class="badge source">📄 {s}</span>' for s in sources)}
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
    </div>
  </div>
</header>

<nav>
  <div class="nav-inner">
    <a class="nav-link" href="#overview">📋 Índice</a>
    {"".join(f'<a class="nav-link" href="#{t["id"]}">{t["title"]}</a>' for t in topics)}
    <a class="nav-link" href="#exam">🎓 Simulacro</a>
  </div>
</nav>

<main>
  {_section_overview(topics)}
  {sections}
  {_section_exam()}
</main>

{_script(all_questions_js)}
</body>
</html>"""


# ── Overview ──────────────────────────────────────────────────────────────────

def _section_overview(topics: list[dict]) -> str:
    items = "".join(
        f"""<div class="module">
          <h3><a href="#{t['id']}" class="topic-link">
            <span class="topic-num">{i+1}</span>{t['title']}
          </a></h3>
          <div class="pills">
            {"".join(f'<span class="pill">{s["title"]}</span>' for s in t.get("subtopics", []))}
          </div>
        </div>"""
        for i, t in enumerate(topics)
    )
    return f"""<section id="overview">
  <div class="section-title">
    <div><h2>📋 Índice de contenidos</h2>
    <p>Visión general. Haz clic en un tema para ir directamente.</p></div>
  </div>
  <div class="grid3">{items}</div>
</section>"""


# ── Topic section ─────────────────────────────────────────────────────────────

def _section_topic(topic: dict, idx: int) -> str:
    tid = topic["id"]
    title = topic["title"]
    subtopics = topic.get("subtopics", [])
    sisters = topic.get("sisters", [])
    questions = topic.get("questions", [])
    flashcards = topic.get("flashcards", [])

    subtopic_tabs = _subtopic_tabs(tid, subtopics)
    sisters_html = _sisters_table(sisters)
    flashcards_html = _flashcards_grid(tid, flashcards)
    quiz_html = _quiz_section(tid, questions)

    return f"""<section id="{tid}">
  <div class="section-title">
    <div>
      <h2><span class="topic-num-lg">{idx+1}</span>{title}</h2>
      <p>{"  ·  ".join(s["title"] for s in subtopics)}</p>
    </div>
  </div>

  {subtopic_tabs}

  {f'''<div class="subsection">
    <div class="section-title"><div>
      <h3>🔗 Preguntas hermanas</h3>
      <p>Variantes posibles del mismo concepto en el examen.</p>
    </div></div>
    {sisters_html}
  </div>''' if sisters_html else ''}

  <div class="subsection">
    <div class="section-title"><div>
      <h3>🃏 Flashcards — {title}</h3>
      <p>Haz clic en cada tarjeta para ver la definición.</p>
    </div></div>
    {flashcards_html}
  </div>

  <div class="subsection">
    <div class="section-title"><div>
      <h3>❓ Quiz — {title}</h3>
      <p>Preguntas tipo test con feedback inmediato.</p>
    </div></div>
    {quiz_html}
  </div>

</section>"""


# ── Subtopic tabs ─────────────────────────────────────────────────────────────

def _subtopic_tabs(tid: str, subtopics: list[dict]) -> str:
    if not subtopics:
        return ""

    tabs = "".join(
        f'<button class="tab{" active" if i == 0 else ""}" '
        f'onclick="openTab(\'{sub["id"]}\', this, \'{tid}\')">{sub["title"]}</button>'
        for i, sub in enumerate(subtopics)
    )

    contents = "".join(
        f'<div class="tab-content{" active" if i == 0 else ""}" id="{sub["id"]}">'
        f'{_subtopic_content(sub)}'
        f'</div>'
        for i, sub in enumerate(subtopics)
    )

    return f"""<div class="subtopic-block">
  <div class="tabs">{tabs}</div>
  {contents}
</div>"""


def _subtopic_content(sub: dict) -> str:
    explanation = sub.get("explanation", "")
    concepts = sub.get("concepts", [])
    confusions = sub.get("confusions", [])

    concepts_rows = "".join(
        f"<tr><td><strong>{c.get('concept','')}</strong></td><td>{c.get('definition','')}</td></tr>"
        for c in concepts
    )

    confusions_rows = "".join(
        f"<tr><td>{c.get('a','')}</td><td>{c.get('b','')}</td><td>{c.get('difference','')}</td></tr>"
        for c in confusions
    )

    concepts_table = f"""<div class="panel" style="margin-top:14px">
      <h4>🔑 Conceptos clave</h4>
      <table>
        <tr><th>Concepto</th><th>Definición</th></tr>
        {concepts_rows}
      </table>
    </div>""" if concepts_rows else ""

    confusions_table = f"""<div class="panel" style="margin-top:14px">
      <h4>⚠️ Confusiones frecuentes</h4>
      <table>
        <tr><th>Concepto A</th><th>Concepto B</th><th>Diferencia clave</th></tr>
        {confusions_rows}
      </table>
    </div>""" if confusions_rows else ""

    return f"""<div class="subtopic-content">
  <div class="panel explanation-panel">
    <div class="explanation-text">{_paragraphs(explanation)}</div>
  </div>
  {concepts_table}
  {confusions_table}
</div>"""


# ── Sister questions ──────────────────────────────────────────────────────────

def _sisters_table(sisters: list[dict]) -> str:
    if not sisters:
        return ""
    rows = "".join(
        f"<tr><td>{s.get('question','')}</td><td>{s.get('variants','')}</td>"
        f"<td><strong>{s.get('key_idea','')}</strong></td></tr>"
        for s in sisters
    )
    return f"""<div class="panel">
    <table>
      <tr><th>Si preguntan...</th><th>También podrían preguntar...</th><th>Idea clave</th></tr>
      {rows}
    </table>
  </div>"""


# ── Flashcards ────────────────────────────────────────────────────────────────

def _flashcards_grid(tid: str, flashcards: list[dict]) -> str:
    if not flashcards:
        return "<p style='color:var(--muted)'>No se generaron flashcards para este tema.</p>"
    cards = "".join(
        f"""<div class="flip" onclick="this.classList.toggle('flipped')">
          <div class="flip-inner">
            <div class="flip-front">
              <strong>{fc.get('front','')}</strong>
              <p>Haz clic para ver</p>
            </div>
            <div class="flip-back"><p>{fc.get('back','')}</p></div>
          </div>
        </div>"""
        for fc in flashcards
    )
    return f'<div class="flashcards">{cards}</div>'


# ── Per-topic quiz ────────────────────────────────────────────────────────────

def _quiz_section(tid: str, questions: list[dict]) -> str:
    if not questions:
        return "<p style='color:var(--muted)'>No se generaron preguntas para este tema.</p>"
    cards = ""
    for i, q in enumerate(questions):
        qid = f"{tid}_q{i}"
        opts = "".join(
            f'<div class="quiz-option" onclick="answer(\'{qid}\',{j},{q["correct"]},this,\'{_escape(q.get("explanation",""))}\')">'
            f'{chr(97+j)}. {opt}</div>'
            for j, opt in enumerate(q["options"])
        )
        cards += f"""<div class="quiz-card" id="card-{qid}">
          <h3>{i+1}. {q["question"]}</h3>
          <div class="opciones">{opts}</div>
          <div class="quiz-note" id="note-{qid}"></div>
        </div>"""
    return f'<div class="quiz-grid">{cards}</div>'


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
        <label>Preguntas</label>
        <input type="number" id="examCount" value="20" min="5" max="200" style="width:80px">
      </div>
      <label class="toggle-label"><input type="checkbox" id="examShuffle" checked> Mezclar</label>
      <label class="toggle-label"><input type="checkbox" id="examShowTopic"> Mostrar tema</label>
      <button class="primary" onclick="startExam()">▶ Iniciar</button>
      <button onclick="gradeExam()">✅ Corregir</button>
      <button onclick="resetExam()">🔄 Reiniciar</button>
      <div class="score" id="examScore">Sin iniciar</div>
    </div>
  </div>
  <div id="examGrid" class="quiz-grid"></div>
  <div id="examBreakdown" class="result" style="display:none;margin-top:14px"></div>
</section>"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _paragraphs(text: str) -> str:
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    return "".join(f"<p>{p}</p>" for p in parts) if parts else f"<p>{text}</p>"


def _escape(text: str) -> str:
    return text.replace("'", "\\'").replace('"', '\\"').replace("\n", " ")


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
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{
  margin:0;
  font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  color:var(--text);
  background:radial-gradient(circle at 10% 0%,#dbeafe 0%,rgba(219,234,254,0) 34%),
             radial-gradient(circle at 90% 8%,#ccfbf1 0%,rgba(204,251,241,0) 34%),
             var(--bg);
  line-height:1.55;
}
header,main,.nav-inner{max-width:1220px;margin:0 auto}
header{padding:34px 20px 18px}
.hero{display:grid;grid-template-columns:1.35fr .65fr;gap:16px}
.hero-card,.stat-card,.panel,.card,.quiz-card,.module{
  background:rgba(255,255,255,.94);border:1px solid var(--border);
  border-radius:var(--radius);box-shadow:var(--shadow)
}
.hero-card{padding:30px}
.sf-badge{display:inline-block;background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;
  border-radius:999px;padding:5px 12px;font-size:.8rem;font-weight:800;margin-bottom:12px}
h1{font-size:clamp(2rem,4vw,4rem);line-height:.96;letter-spacing:-.065em;margin:0 0 12px}
h3,h4{letter-spacing:-.025em;margin:0 0 10px}
h4{font-size:1rem;color:var(--text)}
.subtitle{color:var(--muted);font-size:1.05rem;margin:0 0 14px}
.badges{display:flex;flex-wrap:wrap;gap:7px;margin-top:14px}
.badge{display:inline-flex;border-radius:999px;font-weight:900;align-items:center;
  padding:6px 11px;background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;font-size:.82rem}
.badge.source{background:#f3e8ff;color:#6d28d9;border-color:#ddd6fe}
.stat-grid{display:grid;gap:12px}
.stat-card{padding:18px}
.stat-number{font-size:2.1rem;font-weight:950;letter-spacing:-.05em}
.stat-label{color:var(--muted);font-size:.93rem}
nav{position:sticky;top:0;z-index:50;background:rgba(244,247,251,.91);
  backdrop-filter:blur(12px);border-top:1px solid rgba(255,255,255,.55);
  border-bottom:1px solid var(--border)}
.nav-inner{padding:11px 20px;display:flex;gap:9px;overflow-x:auto;scrollbar-width:none}
.nav-inner::-webkit-scrollbar{display:none}
.nav-link,button{
  border:1px solid var(--border);background:#fff;color:var(--text);border-radius:999px;
  padding:9px 13px;font-weight:850;white-space:nowrap;cursor:pointer;font-size:.9rem;
  transition:transform .12s ease,border .18s ease,background .18s ease;
  text-decoration:none;display:inline-flex;align-items:center
}
.nav-link:hover,button:hover{transform:translateY(-1px);border-color:#93c5fd;background:#f8fbff}
button.primary{background:var(--primary);color:#fff;border-color:var(--primary)}
button.primary:hover{background:var(--primary-dark)}
main{padding:24px 20px 70px}
section{margin:32px 0;padding-top:8px}
.subsection{margin-top:24px}
.section-title{display:flex;justify-content:space-between;align-items:end;gap:16px;margin:0 0 14px}
.section-title h2{margin:0;font-size:clamp(1.45rem,2.3vw,2.25rem);letter-spacing:-.045em;line-height:1.05}
.section-title h3{margin:0;font-size:1.25rem}
.section-title p{margin:6px 0 0;color:var(--muted);max-width:850px}
.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.panel,.card,.quiz-card,.module{padding:18px}
.topic-num{display:inline-flex;align-items:center;justify-content:center;
  width:26px;height:26px;background:var(--primary);color:#fff;border-radius:8px;
  font-size:.8rem;font-weight:900;margin-right:10px;flex-shrink:0}
.topic-num-lg{display:inline-flex;align-items:center;justify-content:center;
  width:38px;height:38px;background:var(--primary);color:#fff;border-radius:12px;
  font-size:1.05rem;font-weight:900;margin-right:12px;flex-shrink:0;vertical-align:middle}
.topic-link{color:var(--text);text-decoration:none;display:flex;align-items:center}
.topic-link:hover{color:var(--primary)}
.pills{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.pill{display:inline-flex;border-radius:999px;font-weight:800;align-items:center;
  padding:4px 10px;font-size:.77rem;background:#eef2ff;color:#3730a3;border:1px solid #c7d2fe}
/* Tabs */
.subtopic-block{margin-bottom:10px}
.tabs{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}
.tab{border:1px solid var(--border);background:#fff;color:var(--text);
  border-radius:999px;padding:8px 14px;font-weight:800;cursor:pointer;font-size:.88rem;
  transition:all .15s ease}
.tab.active{background:var(--primary);color:#fff;border-color:var(--primary)}
.tab-content{display:none}.tab-content.active{display:block}
/* Subtopic content */
.subtopic-content{display:grid;gap:14px}
.explanation-panel{border-left:4px solid var(--primary)}
.explanation-text p{margin:0 0 10px;color:var(--text);line-height:1.65}
.explanation-text p:last-child{margin-bottom:0}
/* Tables */
table{width:100%;border-collapse:collapse;border:1px solid var(--border);
  border-radius:18px;overflow:hidden;background:#fff}
th,td{padding:11px 13px;border-bottom:1px solid var(--border);text-align:left;vertical-align:top}
th{background:#f8fafc;font-weight:800}
tr:last-child td{border-bottom:0}
/* Quiz */
.quiz-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px}
.quiz-card{padding:18px}
.quiz-card h3{margin:0 0 12px;font-size:.97rem;line-height:1.4;letter-spacing:-.01em}
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
/* Flashcards */
.flashcards{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.flip{perspective:1000px;min-height:160px;cursor:pointer}
.flip-inner{position:relative;width:100%;min-height:160px;transform-style:preserve-3d;
  transition:transform .45s ease}
.flip.flipped .flip-inner{transform:rotateY(180deg)}
.flip-front,.flip-back{position:absolute;inset:0;border-radius:20px;border:1px solid var(--border);
  background:#fff;padding:18px;backface-visibility:hidden;box-shadow:var(--shadow);
  display:flex;flex-direction:column;justify-content:center}
.flip-back{transform:rotateY(180deg);background:#f0fdf4;border-color:#86efac}
.flip-front strong{font-size:1rem;color:var(--primary);display:block;margin-bottom:6px}
.flip-front p{color:var(--muted);font-size:.85rem;margin:0}
.flip-back p{color:#14532d;margin:0;font-size:.92rem;line-height:1.5}
/* Exam */
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
@media(max-width:900px){
  .hero,.grid2,.grid3{grid-template-columns:1fr}
  .score{margin-left:0;width:100%;text-align:center}
  .section-title{display:block}
}
@media print{nav,.exam-toolbar{display:none}body{background:white}}
</style>"""


# ── JavaScript ────────────────────────────────────────────────────────────────

def _script(questions_js: str) -> str:
    return f"""<script>
const QUESTIONS = {questions_js};

// Tab switching (scoped per topic section)
function openTab(tabId, btn, sectionId) {{
  const section = document.getElementById(sectionId);
  section.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  section.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById(tabId).classList.add('active');
}}

// Per-topic quiz
function answer(qid, selected, correct, el, explanation) {{
  const card = document.getElementById('card-' + qid);
  const note = document.getElementById('note-' + qid);
  card.querySelectorAll('.quiz-option').forEach((opt, i) => {{
    opt.style.pointerEvents = 'none';
    if (i === correct) opt.classList.add('correct');
  }});
  if (selected !== correct) el.classList.add('wrong');
  note.textContent = (selected === correct ? '✅ Correcto. ' : '❌ Incorrecto. ') + explanation;
  note.className = 'quiz-note show ' + (selected === correct ? 'ok' : 'bad');
}}

// Global exam
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
      <h3>${{idx + 1}}. ${{q.q}}</h3>
      ${{showTopic ? `<div style="margin-bottom:8px"><span class="pill" style="background:var(--purple-bg);color:#6d28d9">${{q.topicName}}</span></div>` : ''}}
      <div class="opciones">
        ${{q.options.map((op, i) => `
          <div class="quiz-option" onclick="answerExam(${{idx}},${{i}},this)">${{String.fromCharCode(97+i)}}. ${{op}}</div>
        `).join('')}}
      </div>
      <div class="quiz-note" id="exam-note-${{idx}}"></div>
    </div>
  `).join('');
  updateScore();
  document.getElementById('examBreakdown').style.display = 'none';
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
      op.style.pointerEvents = 'none';
      if (i === q.answer) op.classList.add('correct');
    }});
    if (sel !== null && sel !== q.answer) card.querySelectorAll('.quiz-option')[sel].classList.add('wrong');
    const ok = sel === q.answer;
    note.textContent = sel === null
      ? '⚠️ Sin responder. Correcta: ' + String.fromCharCode(97 + q.answer) + '. ' + q.why
      : (ok ? '✅ Correcto. ' : '❌ Incorrecto. Correcta: ' + String.fromCharCode(97 + q.answer) + '. ') + q.why;
    note.className = 'quiz-note show ' + (ok ? 'ok' : 'bad');
    if (!byTopic[q.topicName]) byTopic[q.topicName] = {{total:0, correct:0}};
    byTopic[q.topicName].total++;
    if (ok) byTopic[q.topicName].correct++;
  }});
  const total = examQ.length;
  const correct = examState.reduce((acc, val, idx) => acc + (val === examQ[idx].answer ? 1 : 0), 0);
  const pct = Math.round((correct / total) * 100);
  document.getElementById('examScore').textContent = `Resultado: ${{correct}}/${{total}} · ${{pct}}%`;
  const rows = Object.entries(byTopic).map(([topic, v]) => {{
    const p = Math.round((v.correct/v.total)*100);
    return `<tr><td>${{topic}}</td><td>${{v.correct}}/${{v.total}}</td><td>${{p}}%</td></tr>`;
  }}).join('');
  const box = document.getElementById('examBreakdown');
  box.style.display = 'block';
  box.className = 'result ' + (pct >= 85 ? 'good' : pct >= 65 ? 'warn' : 'bad');
  box.innerHTML = `<strong>Desglose por tema:</strong><table><tr><th>Tema</th><th>Aciertos</th><th>%</th></tr>${{rows}}</table>`;
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
</script>"""