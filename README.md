# Chat IDE — Local AI Coding Workspace

A browser-based IDE where you edit a real codebase by *talking to it*. A file tree on the
left, a chat panel on the right, and a local LLM that proposes changes as reviewable
diffs — accept or reject each hunk before anything touches disk. Runs entirely on your
machine against Ollama; no cloud, no API keys.

## Features

- **File-tree workspace** — browse and open files from a project root, VS Code-style dark UI.
- **Diff-based edits** — in edit mode the model returns proposed changes as colored
  add/delete hunks with checkboxes; nothing is written until you approve.
- **Chat over your code** — ask questions or request edits in plain language.
- **Local models** — swap chat/edit models freely (gemma3, DeepSeek-R1-Distill, Qwen3, …).

## Stack

- Backend: Python + Flask (`app.py`)
- Frontend: single-page vanilla JS + HTML (`static/index.html`)
- Inference: Ollama (local)

## Run

```bash
pip install flask requests
# Ollama running locally with your chosen model pulled, then:
python run.py        # open the served page in your browser
```
