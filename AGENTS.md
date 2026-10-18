# Repository Guidelines

## Project Structure & Module Organization

This repository implements the same Parachute S.A. assistant with three orchestration patterns:

- `centralizada.py`: one supervisor coordinating workers through `as_tool()`.
- `jerarquica.py`: root manager, specialized managers, and workers.
- `descentralizada.py`: peer agents connected with `handoff()`.
- `shared/parachute.py`: shared Open-Meteo integration, FAQ lookup, safety rules, and appointment scheduling. Keep business logic here so architectures do not diverge.
- `tests/`: deterministic unit tests.
- `diagramas/`: Mermaid architecture diagrams.
- `respuestas_hdt5.md` and `respuestas_hdt5.pdf`: assignment explanations and deliverable.

## Build, Test, and Development Commands

Use the HDT4 virtual environment from the repository root:

```bash
source ../ai-function-calls/.venv/bin/activate
pip install -r requirements.txt
```

Run the automated tests:

```bash
python -m unittest discover -s tests -v
```

Run an architecture with a date-based request:

```bash
python centralizada.py "Quiero calendarizar una cita el 2026-09-20"
python jerarquica.py "Quiero calendarizar una cita el 2026-09-20"
python descentralizada.py "Quiero calendarizar una cita el 2026-09-20"
```

Check all threshold and date cases with `python probar_todos_casos.py`; add `--live` for Open-Meteo calls. Regenerate the PDF with `python generar_pdf.py`.

## Coding Style & Naming Conventions

Use Python 3.10+ with four-space indentation, type hints, and short docstrings for tools. Use `snake_case` for functions and variables, `PascalCase` for dataclasses and agent classes, and descriptive agent names ending in `Agent`, `Manager`, `Supervisor`, or `Worker`.

## Testing Guidelines

Tests use the standard library `unittest`. Name files `test_*.py` and test methods `test_*`. Cover every safety threshold, date boundary, invalid input, and scheduling guard. Do not require live API access in unit tests; mock network calls instead.

## Security & Configuration

Copy `.env.example` to `.env`; never commit API keys. The application supports the HDT4 Groq-compatible configuration. Never bypass the deterministic weather check or schedule an unsafe appointment.

## Commit & Pull Request Guidelines

No commit history exists yet, so establish imperative, focused messages such as `Add decentralized handoff tests`. Pull requests should describe the architecture affected, include test output, and update diagrams or the PDF when behavior or deliverables change.
