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

## N+N-1 retention (now wired in)

`Dockerfile` pulls `...:latest` as a `previous` stage and merges its
`build_latest/` into the new image's `build/` before serving. The workflow
retags the just-deployed image as `:latest` after `porter apply` so the
*next* build sees this build as its previous.

Two prerequisites:

- The workflow needs `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` GH
  secrets with `ecr:BatchGetImage` and `ecr:PutImage` on `static-app`.
- `:latest` must exist before the first N+N-1 build. Seed it once:
  ```
  MANIFEST=$(aws ecr batch-get-image --repository-name static-app \
    --image-ids imageTag=<existing-sha> --query 'images[0].imageManifest' --output text)
  aws ecr put-image --repository-name static-app --image-tag latest --image-manifest "$MANIFEST"
  ```

The **first deploy after enabling this** still ships only N's assets — its
`previous` image was built before `build_latest/` existed. From the **second
deploy onward** the new image carries N and N-1 chunks.

Test sequence (after the second N+N-1-built deploy is live):

1. Start `probe.py`. It pins to the current hashes — call them v_a.
2. Push another commit. New deploy is v_b.
3. Probe should report `[DEPLOY DETECTED]` but the v_a URLs should keep returning 200 (v_b's image carries v_a's `build_latest/`).
4. Push one more commit (v_c). Now v_a hashes start returning 404 — v_c's image carries v_c + v_b, but not v_a. This is the N-2 boundary: N+N-1 covers exactly one deploy back.

## Knobs to add next

- `preStop: sleep N` and a SIGTERM handler in `server.js` to compare against the routing-race vs. graceful-shutdown story.
- Sticky-session annotation on the Ingress.
