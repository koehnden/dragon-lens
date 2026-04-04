# Streamlit Community Cloud Demo Deployment

Dashboard-only public demo deployment for DragonLens.

## Summary

- Deploy the existing Streamlit app entrypoint at `src/ui/app.py`.
- Set `APP_MODE=public_demo`.
- Do not configure `BACKEND_API_BASE_URL` for the hosted demo.
- Publish dashboard data by committing `demo_data/dashboard_snapshot.json`.
- Local/admin mode keeps the full live app and API-backed workflow.

## Files

- Entry point: `src/ui/app.py`
- Community Cloud dependency file: `src/ui/requirements.txt`
- Demo snapshot file: `demo_data/dashboard_snapshot.json`
- Snapshot export script: `scripts/export_dashboard_snapshot.py`

## 1. Export Demo Data

From your local machine, with your normal local database configured:

```bash
poetry run python scripts/export_dashboard_snapshot.py
```

Export only selected verticals if needed:

```bash
poetry run python scripts/export_dashboard_snapshot.py --vertical-name "Electric Cars"
poetry run python scripts/export_dashboard_snapshot.py --vertical-id 3
```

This updates `demo_data/dashboard_snapshot.json`.

## 2. Commit And Push

```bash
git add demo_data/dashboard_snapshot.json
git commit -m "Update demo dashboard snapshot"
git push
```

Community Cloud redeploys automatically from GitHub after the push.

## 3. Create The Streamlit App

In Streamlit Community Cloud:

1. Create a new app from the GitHub repository.
2. Set the entrypoint file to `src/ui/app.py`.
3. Choose the app URL on `streamlit.app`.

## 4. Configure Secrets

Set the following in the app settings:

```toml
APP_MODE = "public_demo"
```

Optional override if you move the snapshot file:

```toml
DASHBOARD_SNAPSHOT_PATH = "demo_data/dashboard_snapshot.json"
```

No backend API URL is required for the hosted demo.

## 5. Expected Behavior

- The hosted demo only exposes the Dashboard page.
- The dashboard reads from the committed snapshot file, not a live API.
- Local/admin mode continues to use the live API and keeps the full app navigation.

## Update Workflow

1. Refresh local data however you normally do.
2. Export a new dashboard snapshot.
3. Commit and push the updated JSON.
4. Wait for Streamlit Community Cloud to redeploy.

## Notes

- Community Cloud apps sleep after 12 hours of inactivity.
- If the snapshot is missing or empty, the hosted dashboard will show an empty-state message instead of attempting live backend calls.
