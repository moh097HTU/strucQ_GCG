Here's the content in Markdown format for easy copy-pasting:

```markdown
## 2) Download required data files

Your pipeline expects the original dataset file (default: `data/davinci_003_outputs.json`).

If your repo includes `setup.py` that downloads data:

```bash
python setup.py
```

Verify:

```bash
ls -lah data/davinci_003_outputs.json
```

If you already have the dataset elsewhere, you can skip this and pass `--data_path` later.

## 3) Step A (only if needed): Generate GCG logs

If you already have GCG logs under your model folder, skip to Step B.

### 3.1 Run GCG on a small subset first (recommended)

```bash
python test.py \
  --model_name_or_path <path_to_model_dir> \
  --attack gcg \
  --sample_ids 0 1 2 3 4
```

This should create log files under one of these locations:

- `<model_dir>/gcg/.../<sample_id>.jsonl`
- OR `<model_dir>-log/gcg/.../<sample_id>.jsonl`

### 3.2 Confirm logs exist

```bash
find <path_to_model_dir> -type f -path "*gcg*" -name "*.jsonl" | head
# or if your repo uses the -log suffix
find <path_to_model_dir>-log -type f -path "*gcg*" -name "*.jsonl" | head
```

**Tip:** GCG can be expensive. Start with 5–20 samples before scaling up.

## 4) Step B: Export GCG logs to a JSONL dataset

### 4.1 Basic export

```bash
python export_gcg_dataset.py \
  --model_path <path_to_model_dir> \
  --data_path data/davinci_003_outputs.json \
  --out_path gcg_dataset_full.jsonl
```

### 4.2 Export only successful attacks

```bash
python export_gcg_dataset.py \
  --model_path <path_to_model_dir> \
  --data_path data/davinci_003_outputs.json \
  --out_path gcg_dataset_success_only.jsonl \
  --only_success
```

### 4.3 Verify output quickly

```bash
wc -l gcg_dataset_full.jsonl
head -n 1 gcg_dataset_full.jsonl | jq .
```

(If `jq` isn't installed, just do `head -n 1 gcg_dataset_full.jsonl`.)

## 5) Output schema

Each line in the exported JSONL contains one record like:

```json
{
  "id": 0,
  "original_instruction": "...",
  "original_input": "...",
  "original_output": "...",
  "attack_type": "gcg",
  "injected_prompt": "...",
  "gcg_suffix": "...",
  "adv_input": "...",
  "adv_model_output": "...",
  "success_in_response": true,
  "model_name": "...",
  "frontend_delimiters": "..."
}
```

Additional optional fields if delimiters are detected:
- `structured_clean_prompt`
- `structured_adv_prompt`
```