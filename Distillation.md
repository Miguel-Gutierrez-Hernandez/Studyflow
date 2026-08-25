# StudyFlow AI — Distillation Guide 

Goal: use a strong "teacher" model (e.g. `llama3.1:8b`) to generate real
training data from your own study material, fine-tune a smaller "student"
model (e.g. `llama3.2:3b` or `llama3.2:1b`) on it with LoRA, then deploy
the fine-tuned student back into Ollama so day-to-day runs are faster and
cheaper — while staying close to the teacher's quality on YOUR kind of
content (topic detection, subtopics, questions, flashcards).

This is a local, on-device workflow using **MLX** (Apple's ML framework),
which is the right choice on Apple Silicon — much faster than CPU-only
PyTorch and needs no CUDA.

---

## 1. Collect training data with the teacher model

Run the pipeline with a strong model and `distill=True`. Do this across
several real projects/documents — variety matters more than volume.

```python
from pipeline import run

run(
    project_name="distill_source_1",
    files=["some_notes.pdf"],
    model="llama3.1:8b",   # the teacher — must already be pulled in Ollama
    distill=True,
    track=True,
)
```

Repeat for a handful of different documents/subjects. Each run appends to
`distillation_data/records.jsonl` (one JSON object per successful LLM
completion: topic detection, subtopic explanation, sister questions, test
questions, flashcards).

**Rule of thumb:** aim for at least 50-100 recorded examples before your
first fine-tune; more (200+) is better. Since each pipeline run produces
one topic-detection example plus 4 examples per topic (subtopic,
sisters, questions, flashcards), 5-10 runs on real, varied material is
usually enough to get started.

## 2. Export to train/valid splits

```bash
python distill_export.py
```

This writes `distillation_data/train.jsonl` and `distillation_data/valid.jsonl`
in MLX's chat-message format, and prints a per-task breakdown so you can
see if one task type (e.g. `questions`) dominates the dataset — if so,
run a few more pipeline executions to balance it out before fine-tuning.

## 3. Fine-tune with MLX LoRA

Install MLX tooling (Apple Silicon only):
```bash
pip install mlx-lm --break-system-packages
```

Pick a small base model available in MLX format (Hugging Face hub), e.g.
`mlx-community/Llama-3.2-3B-Instruct-4bit`. Run LoRA fine-tuning:

```bash
mlx_lm.lora \
  --model mlx-community/Llama-3.2-3B-Instruct-4bit \
  --train \
  --data distillation_data \
  --iters 300 \
  --batch-size 2 \
  --adapter-path distillation_data/adapters
```

`--data distillation_data` points at the folder containing your
`train.jsonl`/`valid.jsonl`. Adjust `--iters` based on dataset size (a few
hundred iterations is a reasonable start for <500 examples — watch the
validation loss printed during training and stop early if it plateaus or
starts increasing).

## 4. Try the fine-tuned adapter locally

```bash
mlx_lm.generate \
  --model mlx-community/Llama-3.2-3B-Instruct-4bit \
  --adapter-path distillation_data/adapters \
  --prompt "Analyze the following academic content and extract its topic structure..."
```

Compare its JSON output quality against the base model and against the
teacher's own output for the same prompt (from `records.jsonl`).

## 5. Fuse the adapter and deploy back to Ollama

MLX adapters aren't directly usable by Ollama — fuse them into a full
model first, then convert to GGUF (the format Ollama/llama.cpp use):

```bash
# 1. Fuse LoRA weights into the base model
mlx_lm.fuse \
  --model mlx-community/Llama-3.2-3B-Instruct-4bit \
  --adapter-path distillation_data/adapters \
  --save-path distillation_data/fused_model

# 2. Convert to GGUF using llama.cpp's converter
#    (clone https://github.com/ggerganov/llama.cpp if you don't have it)
python llama.cpp/convert_hf_to_gguf.py distillation_data/fused_model \
  --outfile distillation_data/studyflow-student.gguf

# 3. Create an Ollama Modelfile
cat > distillation_data/Modelfile << 'EOF'
FROM ./studyflow-student.gguf
PARAMETER temperature 0.3
EOF

# 4. Register it with Ollama
cd distillation_data
ollama create studyflow-student -f Modelfile
```

## 6. Use the distilled model in StudyFlow

```python
from pipeline import run

run(
    project_name="my_notes",
    files=["notes.pdf"],
    model="studyflow-student",
)
```

## 7. Evaluate before trusting it in production

Don't swap the default model until you've compared quality. Use
`compare_runs.py` to run the same input through the teacher, the original
small model, and the distilled student side by side, then inspect in
MLflow (`mlflow ui --backend-store-uri sqlite:///mlflow.db`):

```bash
python compare_runs.py \
  --files notes.pdf \
  --models llama3.1:8b llama3.2 studyflow-student \
  --base-name eval
```

Compare `n_topics`, `n_questions`, `n_flashcards`, step durations, and —
most importantly — open each generated HTML and read it. Automated
metrics catch structural problems (empty sections, JSON parse failures)
but not subtle quality differences in explanations; a manual read of a
few topics is worth it before switching your default model.

## Notes / caveats

- **This is real ML work, not a one-off script.** Expect to iterate:
  collect more data, retrain, re-evaluate. Treat the first fine-tune as a
  baseline, not a final result.
- **Keep `records.jsonl` around** even after exporting — it's your source
  of truth. `distill_export.py` can be re-run any time (e.g. with a
  different `--valid-fraction`) without losing data.
- **Don't record from the small model** (only enable `distill=True` when
  `model` is your strong teacher) — recording the student's own output
  would just teach it to imitate itself.
- The GGUF conversion step depends on `llama.cpp`'s converter script
  staying compatible with whatever base model you chose; check
  https://github.com/ggerganov/llama.cpp for current supported
  architectures if the conversion fails.