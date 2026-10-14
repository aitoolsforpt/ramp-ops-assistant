# Ramp Operations Assistant — n8n + local LLM

An n8n workflow that receives free-text operational incidents (in Spanish), classifies them with a **local LLM**,
forces a **signed human approval** step for anything serious, routes simulated alerts by severity, keeps a register, and produces an aggregate report.
A small web panel (`panel.py`) lets a supervisor report, approve/reject and read the report from a browser.
It is measured with held-out test cases, not by eye.

▶ **[Watch the 85-second demo](demo-video.mp4)** (no audio, on-screen text)

> **All data is synthetic.** Nothing here comes from a real airline, handler, flight, person or procedure.
> Incident texts, labels and code comments are in Spanish (the language of the use case).

## Why

In ground (ramp) operations, incidents arrive as free text: radio, messages, notes. Sorting them by hand is slow,
and a serious one can slip through. The goal is a uniform register where **a person always sees what is serious**.

## How it works

```mermaid
flowchart TD
    A[Incident, free text<br/>POST /webhook/incidencia] --> B[Build request]
    B --> C[Local model via Ollama<br/>qwen2.5:7b-instruct, JSON output]
    C -->|error / invalid JSON| R[Flag for human review]
    C --> D[Validate JSON]
    D --> E[Safety net: rules raise severity<br/>on critical keywords]
    E --> F[Register]
    R --> F
    F --> G{High or critical?}
    F --> N[Simulated alert routed by severity<br/>GET /webhook/avisos]
    G -->|yes| H[Pending human approval]
    H --> L[GET /webhook/pendientes<br/>approve / reject links]
    L --> M[GET /webhook/decision + approver key<br/>signed: who, role, when]
    G -->|no| I[Registered]
    J[GET /webhook/informe] --> K[Summary by type, severity, status]
    F -.-> K
```

Design principles:
- **An incident is never lost.** If the model fails, it is still registered and goes to human review.
- **Human approval is mandatory** for severity `alta` / `critica`, and it is **signed**: the decision needs an approver key, and the register stores who decided, their role and when. Without a valid key nothing is approved; a decided incident cannot be changed.
- **Hold, not close:** an incident that the safety net flags is never auto-closed.
- **When in doubt, a false alarm beats a missed serious case.** A rule-based safety net runs *after* the model.
- **The classifier is swappable:** the model name and Ollama URL are constants in `n8n/generar_workflow.py`; point them at another local model or a cloud API and regenerate.

Labels: type ∈ `equipaje`, `carga_balance`, `equipo_gse`, `seguridad_prl`, `personal`, `documentacion`, `otro`;
severity ∈ `baja`, `media`, `alta`, `critica`.

## Results

| System / test set | Type | Severity | Approval | Serious cases missed |
|---|---|---|---|---|
| Rules, the 30 cases they were written on | 90 % | 83 % | 97 % | 1 |
| Rules, 15 unseen cases | 20 % | 40 % | 60 % | 6 |
| Local 3B model, 15 unseen cases | 60 % | 40 % | 80 % | 1 |
| Local 7B model, 15 unseen cases | 67 % | 67 % | 80 % | 1 |
| 7B + safety net, validation (15) | 67 % | 80 % | 87 % | 0 |
| **7B + safety net, final test (15, run once)** | **80 %** | **80 %** | **93 %** | **0** |

What it shows: hand-written rules overfit (90 % → 20 % on unseen cases); the model generalises better; a simple
safety net removes the grave error. The final-test row is the trustworthy one: prompt and rules were not touched after seeing it.
The n8n workflow reproduces the Python script's numbers.

## Limitations (honest)

- **Small sample:** 15 + 15 cases, written by the same person who built the system. Numbers are indicative, not a guarantee.
  Next step: cases written by someone else, a larger or fine-tuned model.
- Remaining errors: type confusion (documentation vs. load) and severity somewhat over-estimated (T02, T05, T08).
- Persistence is n8n's built-in SQLite workflow data: fine for a demo, not for production (use Postgres or a spreadsheet).
- **Alerts are simulated.** The routing (critical → shift lead, high → supervisor) is real, but the node only writes to an alert log (`/webhook/avisos`). Replace it with Telegram / email / Slack using a team or service account, not a personal one.
- **Access control is minimal.** Approver keys in `n8n/generar_workflow.py` are demo values: change them. Reading the report, pending list and alert log is open to anyone who can reach the server. Run it on localhost or behind your own authentication; do not expose it to the internet as is.
- **No outgoing report yet.** The report is pulled (`/webhook/informe`), not pushed. A scheduled email per shift with the summary and unresolved pending items is the next step.

## Run it

Requirements: Node.js, [Ollama](https://ollama.com), Python 3 (standard library only).

```bash
ollama pull qwen2.5:7b-instruct

# 1. Start n8n (local, no keys needed) and create the local owner account on first visit
npx n8n start                      # http://localhost:5678

# 2. Import and publish the workflow
npx n8n import:workflow --input=n8n/workflow.json
npx n8n publish:workflow --id=opsAsistenteRampa01     # then restart n8n

# 3. Send the held-out cases and score them
python enviar_a_n8n.py datos/prueba_final_sintetica.json resultados/n8n_prueba_final.json
python -I evaluar.py resultados/n8n_prueba_final.json datos/prueba_final_sintetica.json
```

Try one incident by hand:

```bash
curl -X POST http://127.0.0.1:5678/webhook/incidencia -H "Content-Type: application/json" \
  -d '{"id":"DEMO1","texto":"Sale humo de una bodega durante la carga."}'
curl http://127.0.0.1:5678/webhook/pendientes   # approve / reject links (replace TU_CLAVE with an approver key)
curl http://127.0.0.1:5678/webhook/avisos       # simulated alerts by severity
python panel.py                                 # web panel on http://127.0.0.1:8765
curl http://127.0.0.1:5678/webhook/informe      # report
```

## Repository layout

| Path | What |
|---|---|
| `n8n/workflow.json`, `n8n/generar_workflow.py` | The workflow and the generator that builds it (edit model/URL there) |
| `clasificar_ollama.py`, `red_seguridad.py`, `aplicar_red.py` | Reference classifier, safety net, and applying it to saved outputs |
| `evaluar.py` | Evaluator (type / severity / approval accuracy, missed serious cases) |
| `enviar_a_n8n.py` | Sends a case set to the webhook and stores the answers |
| `panel.py` | Small local web panel (report an incident, approve/reject with approver key, simulated alerts, report) |
| `datos/` | Synthetic cases: 30 development, 15 validation, 15 final test |
| `resultados/` | Saved model and workflow outputs behind the table above |

## License

MIT — see `LICENSE`.
