# AI-Job-Hunter Backend Foundation

This directory contains the first minimal FastAPI foundation for the AI-Job-Hunter hackathon MVP.

The implementation uses deterministic mock agents behind stable interfaces. Replace the mocks with MiMo-powered agents without changing the API contract.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn backend.app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`.

## API

`POST /api/v1/job-fit` accepts one student profile and one target job. It returns source checks, a fit report, resume suggestions, interview questions, warnings, and an execution log.

## Test

```powershell
$env:PYTHONPATH = "."
python -m unittest discover -s backend/tests -v
```

## Next Steps

1. Add real job fixtures and source verification.
2. Replace the three mock agents with MiMo clients.
3. Persist requests, reports, source snapshots, and failures.
4. Add the React workbench UI.
