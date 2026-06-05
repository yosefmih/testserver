# static-app

Minimal reproduction of the customer-portal 404 pattern:

- Koa server (same shape as `customer-portal/server.js`) serves `/assets/*` from `build/`, falls back to `index.html` for everything else, and returns 404 for any path with an extension that misses koa-static.
- `build.sh` generates two content-hashed chunks (`main-<hash>.js`, `vendor-<hash>.js`) and an `index.html` referencing them. Hashes change whenever `BUILD_ID` changes.
- Dockerfile (initial version) carries **only the current build's assets**. No N+N-1 retention, no SIGTERM handler, no preStop. We'll layer those on later.

## Local check

```
npm install
BUILD_ID=v1 sh build.sh && ls build/assets
BUILD_ID=v2 sh build.sh && ls build/assets   # hashes differ from v1
PORT=3000 node server.js &
curl -s localhost:3000/healthz
curl -i localhost:3000/assets/main-<old-v1-hash>.js   # 404 — old hashes not retained
```

## Deploy to Porter

The Dockerfile takes `ARG PORTER_BUILD_ID`. Porter's GHA action forwards any
`PORTER_*` env vars from the workflow into the docker build, so add this to
the deploy job:

```yaml
env:
  PORTER_BUILD_ID: ${{ github.sha }}
```

Each commit then produces a unique `BUILD_ID` and therefore unique asset
hashes. Without this, every deploy ships identical hashes and the demo
doesn't reproduce.

## Repro flow on the cluster

1. Deploy commit A. Load the page in a browser tab. Click "re-fetch main chunk" — should 200.
2. Push commit B (any change is fine). Porter rebuilds — the new pod's `build/assets/` only carries B's hashes.
3. In the still-open commit-A tab, click "re-fetch main chunk" again. It requests `main-<A-hash>.js`. The new pod returns 404. That's the white-screen mechanism.
4. During the rollout itself, additional 404s appear because both A and B pods are briefly in the upstream pool and asset requests cross over.

## Knobs we'll add later

- N+N-1 retention via a `FROM <registry>/static-app:latest AS previous` stage in the Dockerfile.
- `preStop: sleep N` and a SIGTERM handler in `server.js` to compare against the routing-race vs. graceful-shutdown story.
- Sticky-session annotation on the Ingress.
