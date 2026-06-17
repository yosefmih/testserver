# Vendored dependencies

## `porter_sandbox-0.0.1-py3-none-any.whl`

The Porter Sandbox Python SDK (`porter-sandbox`). It is **not published to PyPI
or any package index**, so it is vendored here and installed explicitly in the
`Dockerfile` (and for local dev, see the repo README).

- Source: https://github.com/porter-dev/porter-python-sdk
- Built from commit `200231dc5081db69e93f8188310317be1bb3ea3a`
- Pure-Python; its runtime deps (`httpx`, `pydantic`) are pinned in
  `backend/requirements.txt`.

### Refreshing the wheel

From a checkout of `porter-python-sdk` with build tooling available:

```bash
pip install build
python -m build --wheel
cp dist/porter_sandbox-<version>-py3-none-any.whl \
   path/to/linear-autopilot-productized/backend/vendor/
```

Then bump the filename referenced in the repo root `Dockerfile` if the version
changed.
