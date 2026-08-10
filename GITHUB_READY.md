# GitHub Ready Checklist

**Last updated:** 2026-08-11

Use this before committing and pushing the current FedRepro system.

## Commit

Commit these project files:

- `backend/app/**`
- `backend/alembic/**`
- `backend/tests/**`
- `backend/requirements.txt`
- `backend/.env.example`
- `frontend/src/**`
- `frontend/public/**`
- `frontend/package.json`
- `frontend/package-lock.json`
- `docs/**`
- `tools/**`
- `README.md`
- `.gitignore`
- `.gitattributes`

## Do Not Commit

These are ignored and should stay local:

- `backend/.env`
- `backend/venv/` or any `.venv/`
- `frontend/node_modules/`
- `frontend/dist/`
- `backend/uploads/**` except `backend/uploads/.gitkeep`
- `*.log`
- `fedrepro-legacy-backup-*.zip`

## Verify

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm run build
```

Current expected result:

- backend: 59 passed
- frontend: build passes with one webpack entrypoint size warning

## First Push

```powershell
git init
git add .
git commit -m "Initial FedRepro project"
git branch -M main
git remote add origin <your-github-repo-url>
git push -u origin main
```

## Current Push

For normal updates after the first push:

```powershell
git status --short
git add .
git commit -m "Update diagnosis evidence workflow and documentation"
git push origin main
```
