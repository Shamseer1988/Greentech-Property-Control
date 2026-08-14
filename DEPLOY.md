# Deployment

Full instructions live in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — prerequisites, first install, the production checklist, reverse-proxy shape, systemd units, backups and upgrades.

Quick version (Windows):

```powershell
.\scripts\install-windows.ps1   # deps + frontend build
.\scripts\bootstrap-db.ps1      # schema + seed
.\scripts\start-all.ps1         # run
```

Then open http://localhost:3000 and sign in as `admin` with the `SUPERUSER_PASSWORD` from `backend\.env`.

For day-to-day development workflow see [`DEV.md`](DEV.md).
