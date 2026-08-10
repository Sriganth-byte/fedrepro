# GitHub Ready Checklist

Use this before the first push.

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

## First Push

```powershell
git init
git add .
git commit -m "Initial FedRepro project"
git branch -M main
git remote add origin <your-github-repo-url>
git push -u origin main
```
