"""
generador/html_builder.py — Builds the final study HTML.

Usage:
    from generador.html_builder import build_html
    html = build_html(material)
"""

import json
from datetime import datetime


def build_html(material: dict) -> str:
    title = material["title"]
    topics = material["topics"]
    sources = material.get("sources", [])
    stats = material.get("stats", {})
    date = datetime.now().strftime("%Y-%m-%d")

    questions_js = _serialize_questions(topics)
    flashcards_js = _serialize_flashcards(topics)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{title} — StudyFlow AI</title>
{_css()}
</head>
<body>

<header>
  <div class="hero">
    <div class="hero-card">
      <div class="sf-badge">⚡ StudyFlow AI</div>
      <h1>{title}</h1>
      <p class="subtitle">Auto-generated study material · {date}</p>
      <div class="badges">
        {"".join(f'<span class="badge">{t["title"]}</span>' for t in topics)}
        {"".join(f'<span class="badge source">📄 {s}</span>' for s in sources)}
      </div>
    </div>
    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-number">{stats.get("n_topics", len(topics))}</div>
        <div class="stat-label">topics</div>
      </div>
      <div class="stat-card">
        <div class="stat-number">{stats.get("n_questions", 0)}</div>
        <div class="stat-label">practice questions</div>
      </div>
    </div>
  </div>
</header>

<nav>
  <div class="nav-inner">
    <a class="nav-link" href="#overview">📋 Overview</a>
    {"".join(f'<a class="nav-link" href="#{t["id"]}">{t["title"]}</a>' for t in topics)}
    <a class="nav-link" href="#flashcards">🃏 Flashcards</a>
    <a class="nav-link" href="#exam">🎓 Exam</a>
  </div>
</nav>

<main>
  {_section_overview(topics)}
  {"".join(_section_topic(t, i) for i, t in enumerate(topics))}
  {_section_flashcards(topics)}
  {_section_exam()}
</main>

{_script(questions_js, flashcards_js)}
</body>
</html>"""


# ── Sections ──────────────────────────────────────────────────────────────────

def _section_overview(topics: list[dict]) -> str:
    items = "".join(
        f"""<div class="module">
          <h3><a href="#{t['id']}" class="topic-link">
            <span class="topic-num">{i+1}</span>{t['title']}
          </a></h3>
          <div class="pills">
            {"".join(f'<span class="pill">{st}</span>' for st in t.get("subtopics", []))}
          </div>
        </div>"""
        for i, t in enumerate(topics)
    )
    return f"""<section id="overview">
  <div class="section-title">
    <div>
      <h2>📋 Overview</h2>
      <p>All topics at a glance. Click any topic to jump to it.</p>
    </div>
  </div>
  <div class="grid3">{items}</div>
</section>"""


def _section_topic(topic: dict, idx: int) -> str:
    tid = topic["id"]
    summary = topic.get("summary", "")
    key_points = topic.get("key_points", [])
    keywords = topic.get("keywords", [])
    memory_tricks = topic.get("memory_tricks", [])
    questions = topic.get("questions", [])

    key_points_html = "".join(f"<li>{p}</li>" for p in key_points)

    keywords_html = "".join(
        f"""<div class="keyword-card">
          <strong>{kw.get('term','')}</strong>
          <p>{kw.get('definition','')}</p>
        </div>"""
        for kw in keywords
    )

    tricks_html = "".join(
        f"""<div class="truco">
          <div class="truco-icon">💡</div>
          <div>
            <strong>{tr.get('trick','')}</strong>
            {f'<p class="truco-ejemplo">e.g. {tr.get("example","")}</p>' if tr.get('example') else ''}
          </div>
        </div>"""
        for tr in memory_tricks
    )

    questions_html = _questions_html(tid, questions)

    return f"""<section id="{tid}">
  <div class="section-title">
    <div>
      <h2><span class="topic-num-lg">{idx+1}</span>{topic['title']}</h2>
      {f'<p>{"  ·  ".join(topic.get("subtopics",[]))}</p>' if topic.get("subtopics") else ""}
    </div>
  </div>

  <div class="grid2" style="margin-bottom:14px">
    <div class="panel">
      <h3>📖 Summary</h3>
      <div class="summary-text">{_paragraphs(summary)}</div>
    </div>
    <div class="panel">
      <h3>✅ Key points</h3>
      <ul class="key-list">{key_points_html}</ul>
    </div>
  </div>

  {f'<div class="keywords-section"><h3>🔑 Keywords</h3><div class="keywords-grid">{keywords_html}</div></div>' if keywords_html else ''}
  {f'<div class="trucos-section"><h3>🧠 Memory tricks</h3><div class="trucos-grid">{tricks_html}</div></div>' if tricks_html else ''}
  {f'<div class="test-section"><h3>❓ Quick test — {topic["title"]}</h3>{questions_html}</div>' if questions_html else ''}
</section>"""


def _questions_html(tid: str, questions: list[dict]) -> str:
    if not questions:
        return ""
    cards = ""
    for i, q in enumerate(questions):
        qid = f"{tid}_q{i}"
        options_html = "".join(
            f'<div class="quiz-option" onclick="answer(\'{qid}\',{j},{q["correct"]},this,\'{_escape(q.get("explanation",""))}\')">'
            f'{chr(97+j)}. {opt}</div>'
            for j, opt in enumerate(q["options"])
        )
        cards += f"""<div class="quiz-card" id="card-{qid}">
          <h3>{i+1}. {q["question"]}</h3>
          <div class="opciones">{options_html}</div>
          <div class="quiz-note" id="note-{qid}"></div>
        </div>"""
    return f'<div class="quiz-grid">{cards}</div>'


def _section_flashcards(topics: list[dict]) -> str:
    tabs = "".join(
        f'<button class="tab{" active" if i==0 else ""}" onclick="switchTab(\'{t["id"]}\',this)">{t["title"]}</button>'
        for i, t in enumerate(topics)
    )
    content = "".join(
        f'<div class="tab-content{" active" if i==0 else ""}" id="flash-{t["id"]}">'
        f'<div class="flashcards" id="fc-grid-{t["id"]}"></div>'
        f'</div>'
        for i, t in enumerate(topics)
    )
    return f"""<section id="flashcards">
  <div class="section-title">
    <div>
      <h2>🃏 Flashcards</h2>
      <p>Click a card to flip it. Browse by topic.</p>
    </div>
  </div>
  <div class="tabs" style="margin-bottom:14px">{tabs}</div>
  {content}
</section>"""


def _section_exam() -> str:
    return """<section id="exam">
  <div class="section-title">
    <div>
      <h2>🎓 Exam mode</h2>
      <p>Mixed questions from all topics. Configure and start when ready.</p>
    </div>
  </div>
  <div class="panel" style="margin-bottom:14px">
    <div class="exam-toolbar">
      <div class="exam-control">
        <label>Questions</label>
        <input type="number" id="examCount" value="20" min="5" max="200" style="width:80px">
      </div>
      <label class="toggle-label">
        <input type="checkbox" id="examShuffle" checked> Shuffle
      </label>
      <label class="toggle-label">
        <input type="checkbox" id="examShowTopic"> Show topic
      </label>
      <button class="primary" onclick="startExam()">▶ Start exam</button>
      <button onclick="gradeExam()">✅ Grade</button>
      <button onclick="resetExam()">🔄 Reset</button>
      <div class="score" id="examScore">Not started</div>
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


def _serialize_flashcards(topics: list[dict]) -> str:
    by_topic = {}
    for t in topics:
        cards = []
        for kw in t.get("keywords", []):
            cards.append({"front": kw.get("term", ""), "back": kw.get("definition", "")})
        for tr in t.get("memory_tricks", []):
            if tr.get("trick"):
                cards.append({"front": f"💡 {tr['trick']}", "back": tr.get("example", "")})
        by_topic[t["id"]] = cards
    return json.dumps(by_topic, ensure_ascii=False)


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
.topic-num{display:inline-flex;align-items:center;justify-content:center;
  width:26px;height:26px;background:var(--primary);color:#fff;border-radius:8px;
  font-size:.8rem;font-weight:900;margin-right:10px;flex-shrink:0}
.topic-num-lg{display:inline-flex;align-items:center;justify-content:center;
  width:36px;height:36px;background:var(--primary);color:#fff;border-radius:10px;
  font-size:1rem;font-weight:900;margin-right:12px;flex-shrink:0;vertical-align:middle}
.topic-link{color:var(--text);text-decoration:none;display:flex;align-items:center}
.topic-link:hover{color:var(--primary)}
.pills{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.pill{display:inline-flex;border-radius:999px;font-weight:800;align-items:center;
  padding:4px 10px;font-size:.77rem;background:#eef2ff;color:#3730a3;border:1px solid #c7d2fe}
.summary-text p{margin:0 0 10px;color:var(--text)}
.summary-text p:last-child{margin-bottom:0}
.key-list{margin:0;padding:0 0 0 18px}
.key-list li{margin-bottom:8px;color:var(--text)}
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

def _script(questions_js: str, flashcards_js: str) -> str:
    return f"""<script>
const QUESTIONS = {questions_js};
const FLASHCARDS = {flashcards_js};

// Per-topic quiz
function answer(qid, selected, correct, el, explanation) {{
  const card = document.getElementById('card-' + qid);
  const note = document.getElementById('note-' + qid);
  card.querySelectorAll('.quiz-option').forEach((opt, i) => {{
    opt.style.pointerEvents = 'none';
    if (i === correct) opt.classList.add('correct');
  }});
  if (selected !== correct) el.classList.add('wrong');
  note.textContent = (selected === correct ? '✅ Correct. ' : '❌ Incorrect. ') + explanation;
  note.className = 'quiz-note show ' + (selected === correct ? 'ok' : 'bad');
}}

// Flashcards
function renderFlashcards(tid) {{
  const cards = FLASHCARDS[tid] || [];
  const grid = document.getElementById('fc-grid-' + tid);
  if (!grid) return;
  grid.innerHTML = cards.map((c, i) => `
    <div class="flip" onclick="this.classList.toggle('flipped')">
      <div class="flip-inner">
        <div class="flip-front">
          <strong>${{c.front}}</strong>
          <p>Click to reveal</p>
        </div>
        <div class="flip-back"><p>${{c.back}}</p></div>
      </div>
    </div>
  `).join('');
}}

function switchTab(tid, btn) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('flash-' + tid).classList.add('active');
}}

// Exam mode
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
      ? '⚠️ Unanswered. Correct: ' + String.fromCharCode(97 + q.answer) + '. ' + q.why
      : (ok ? '✅ Correct. ' : '❌ Incorrect. Correct: ' + String.fromCharCode(97 + q.answer) + '. ') + q.why;
    note.className = 'quiz-note show ' + (ok ? 'ok' : 'bad');
    if (!byTopic[q.topicName]) byTopic[q.topicName] = {{total:0, correct:0}};
    byTopic[q.topicName].total++;
    if (ok) byTopic[q.topicName].correct++;
  }});
  const total = examQ.length;
  const correct = examState.reduce((acc, val, idx) => acc + (val === examQ[idx].answer ? 1 : 0), 0);
  const pct = Math.round((correct / total) * 100);
  document.getElementById('examScore').textContent = `Result: ${{correct}}/${{total}} · ${{pct}}%`;
  const rows = Object.entries(byTopic).map(([topic, v]) => {{
    const p = Math.round((v.correct/v.total)*100);
    return `<tr><td>${{topic}}</td><td>${{v.correct}}/${{v.total}}</td><td>${{p}}%</td></tr>`;
  }}).join('');
  const box = document.getElementById('examBreakdown');
  box.style.display = 'block';
  box.className = 'result ' + (pct >= 85 ? 'good' : pct >= 65 ? 'warn' : 'bad');
  box.innerHTML = `<strong>By topic:</strong><table><tr><th>Topic</th><th>Score</th><th>%</th></tr>${{rows}}</table>`;
}}

function resetExam() {{
  document.getElementById('examGrid').innerHTML = '';
  document.getElementById('examScore').textContent = 'Not started';
  document.getElementById('examBreakdown').style.display = 'none';
  examQ = []; examState = [];
}}

function updateScore() {{
  if (!examQ.length) return;
  const answered = examState.filter(x => x !== null).length;
  const correct = examState.reduce((acc, val, idx) => acc + (val === examQ[idx]?.answer ? 1 : 0), 0);
  document.getElementById('examScore').textContent =
    `${{correct}}/${{answered}} correct · ${{answered}}/${{examQ.length}} answered`;
}}

document.addEventListener('DOMContentLoaded', () => {{
  Object.keys(FLASHCARDS).forEach(tid => renderFlashcards(tid));
}});
</script>"""