# EDOS API — Swagger & Postman

The API is FastAPI, so **Swagger/OpenAPI is native**. Two ways to explore it:

## 1. Swagger UI (live, recommended)
Run the app, then open the interactive docs in a browser:
```bash
cd /home/dharmik/Projects/edos
.venv/bin/uvicorn edos.api.app:app --reload
# Swagger UI:  http://localhost:8000/docs
# ReDoc:       http://localhost:8000/redoc
# Raw spec:    http://localhost:8000/openapi.json
```

## 2. Static spec + Postman (share without running)
- **`docs/openapi.json`** — the exported OpenAPI 3 spec. Import into Swagger Editor, Postman, Insomnia, or any OpenAPI tool.
- **`docs/EDOS.postman_collection.json`** — ready-to-import Postman collection with example bodies for all three endpoints. Set the `baseUrl` variable (default `http://localhost:8000`).

## Endpoints (v0.0.1, running on the stub LLM)
| Method | Path | Does |
|--------|------|------|
| POST | `/v1/ask` | Lightweight intent detection |
| POST | `/v1/analyze` | Context → Decision Engine → contract-valid decision (or `needs_clarification` if context is thin) |
| POST | `/v1/verify` | Verification pass: critique + confidence adjust + gated promotion |

> Note: outputs currently come from the deterministic **stub** provider (no live LLM). Shapes are final; the
> real model plugs in at go-live. Regenerate the spec after API changes with:
> `.venv/bin/python -c "import json;from edos.api.app import app;json.dump(app.openapi(),open('docs/openapi.json','w'),indent=2)"`
