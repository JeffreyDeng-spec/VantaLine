# React Preview Deployment Readiness

This deployment track keeps the legacy production root `/` on the FastAPI static
UI until production cutover is explicitly approved. React remains hosted at
`/react-preview/` by default.

## Current Serving Shape

- Legacy production root: `local_inspection_service/static/index.html` served by
  `GET /`.
- React preview shell: `local_inspection_service/frontend/dist/index.html`
  served by `GET /react-preview`, `GET /react-preview/`, and preview deep links.
- React preview assets: `local_inspection_service/frontend/dist/assets/*`
  served by `GET /react-preview/assets/*`.
- Preview assets are hashed by Vite and successful asset responses receive
  immutable cache headers. Preview HTML responses use no-store headers.
- Nginx proxies all paths to the FastAPI service; no nginx path split is needed
  for the preview.

## Preview Deploy

Build and deploy only the preview bundle:

```bash
VANTALINE_SSH_KEY=/path/to/vantaline.pem \
local_inspection_service/scripts/deploy_react_preview.sh preview
```

The command:

1. Runs `npm ci` in `local_inspection_service/frontend`.
2. Runs `npm run build`, using Vite base `/react-preview/`.
3. Backs up the existing remote preview dist under
   `<BACKUP_ROOT>/react-deploy/preview-dist/<timestamp>/dist`.
4. Replaces only
   `<APP_ROOT>/local_inspection_service/frontend/dist`.

Use `--skip-install` only when the checked-out `node_modules` already matches
`package-lock.json`.

## Preview Rollback

Restore the latest preview backup:

```bash
VANTALINE_SSH_KEY=/path/to/vantaline.pem \
local_inspection_service/scripts/deploy_react_preview.sh rollback-preview
```

Restore a specific backup:

```bash
VANTALINE_SSH_KEY=/path/to/vantaline.pem \
local_inspection_service/scripts/deploy_react_preview.sh rollback-preview \
  --backup <BACKUP_ROOT>/react-deploy/preview-dist/<timestamp>
```

Preview rollback only replaces
`<APP_ROOT>/local_inspection_service/frontend/dist`.

## Gated Production Cutover

Do not run this command until production cutover is explicitly approved.

```bash
VANTALINE_SSH_KEY=/path/to/vantaline.pem \
local_inspection_service/scripts/deploy_react_preview.sh cutover \
  --confirm-production-cutover
```

The cutover command is intentionally not the default. It:

1. Runs `npm ci`.
2. Runs TypeScript checking.
3. Builds React with router basename `/` and Vite base `/static/` into
   `dist-production`.
4. Backs up the complete remote legacy static directory under
   `<BACKUP_ROOT>/react-deploy/production-static/<timestamp>/static`.
5. Enables the gated FastAPI production SPA fallback by writing the systemd
   drop-in `30-react-production.conf` with
   `VANTALINE_REACT_PRODUCTION_SPA=1`.
6. Replaces `static/index.html` and `static/assets/*`, leaving
   `/react-preview/` available for debugging.

This approach matches the existing FastAPI root route: `/` still serves
`local_inspection_service/static/index.html`, while React production assets load
from `/static/assets/*`. Production deep-link refreshes such as `/pipeline` are
served by the disabled-by-default fallback only after the cutover command enables
`VANTALINE_REACT_PRODUCTION_SPA=1`.

## Production Rollback

Restore the latest production static backup:

```bash
VANTALINE_SSH_KEY=/path/to/vantaline.pem \
local_inspection_service/scripts/deploy_react_preview.sh rollback-production
```

Restore a specific backup:

```bash
VANTALINE_SSH_KEY=/path/to/vantaline.pem \
local_inspection_service/scripts/deploy_react_preview.sh rollback-production \
  --backup <BACKUP_ROOT>/react-deploy/production-static/<timestamp>
```

Production rollback replaces
`/opt/vantaline/app/local_inspection_service/static` from the selected backup,
removes the `30-react-production.conf` systemd drop-in, reloads systemd, and
restarts the service so legacy 404 behavior is restored.

## Smoke Checks

After a preview deploy, verify:

```bash
curl -fsSI "$VANTALINE_BASE_URL/"
curl -fsSI "$VANTALINE_BASE_URL/react-preview/"
curl -fsSI "$VANTALINE_BASE_URL/react-preview/pipeline"
curl -fsS "$VANTALINE_BASE_URL/api/auth/status"
```

Expected:

- `/` remains the legacy static shell and is not replaced by the React preview
  deploy.
- `/react-preview/` and a preview deep link return the React shell.
- The React shell references hashed assets under `/react-preview/assets/`.
- Public auth status still returns JSON from the API.
- The preview backup path printed by the deploy command exists on the deployment host.

Before a future production cutover, capture checksums for both
`static/index.html` and `frontend/dist/index.html`; after preview deploy, only
`frontend/dist/index.html` should change.

Before approving cutover, dry-run the production build and confirm the generated
JavaScript does not contain the preview basename:

```bash
cd local_inspection_service/frontend
npm run build:production-cutover
rg 'basename:`/react-preview`|basename:"/react-preview"|basename="/react-preview"' dist-production/assets
```

The `rg` command should return no matches.
