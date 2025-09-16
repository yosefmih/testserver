#!/usr/bin/env python3
import os
import json
import time
import uuid
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


# Configuration
VOLUME_MOUNT_POINT = os.environ.get("VOLUME_MOUNT_POINT", "/tmp/nvme")
DEFAULT_DEPENDENCIES = {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "typescript": "^5.4.0",
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "lucide-react": "^0.452.0",
    "react-router-dom": "^6.22.0"
}

# Tooling
TSGO = os.environ.get("TSGO_PATH") or "/usr/local/bin/tsgo"


def ensure_bun_cache_env(base_env: dict) -> dict:
    env = base_env.copy()
    env.setdefault("BUN_INSTALL_CACHE_DIR", f"{VOLUME_MOUNT_POINT}/bun/install")
    env.setdefault("BUN_RUNTIME_TRANSPILER_CACHE_PATH", f"{VOLUME_MOUNT_POINT}/bun/transpiler-cache")
    env.setdefault("BUN_RUNTIME_CACHE_PATH", f"{VOLUME_MOUNT_POINT}/bun/runtime-cache")
    # Ensure directories exist
    Path(env["BUN_INSTALL_CACHE_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(env["BUN_RUNTIME_TRANSPILER_CACHE_PATH"]).mkdir(parents=True, exist_ok=True)
    Path(env["BUN_RUNTIME_CACHE_PATH"]).mkdir(parents=True, exist_ok=True)
    return env


def safe_join(root: Path, relative_path: str) -> Path:
    # Minimal safety: prevent absolute paths and parent traversal
    p = Path(relative_path)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"unsafe path: {relative_path}")
    return (root / p).resolve()


def write_files(work_dir: Path, files):
    for f in files:
        rel_path = f.get("path")
        contents = f.get("contents", "")
        if not rel_path:
            raise ValueError("file entry missing 'path'")
        target = safe_join(work_dir, rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents)


def write_package_json(work_dir: Path, deps: dict | None):
    pkg = {
        "name": f"fast-tsc-run",
        "private": True,
        "version": "1.0.0",
        "type": "module",
        "dependencies": deps or DEFAULT_DEPENDENCIES,
    }
    (work_dir / "package.json").write_text(json.dumps(pkg, indent=2))


def run(cmd: list[str], cwd: Path, env: dict) -> tuple[int, str, str, int]:
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=str(cwd), env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ms = int((time.perf_counter() - t0) * 1000)
    return ms, proc.stdout, proc.stderr, proc.returncode


def bun_install(work_dir: Path, env: dict) -> tuple[int, str, str, int]:
    cmd = [
        "bun", "install",
        "--ignore-scripts", "--no-progress", "--no-summary", "--no-verify",
        "--backend=hardlink",
    ]
    return run(cmd, cwd=work_dir, env=env)


def run_tsgo(work_dir: Path, files: list[str], env: dict) -> tuple[int, str, str, int]:
    cmd = [
        TSGO,
        "--allowJs",
        "--skipLibCheck",
        "--noEmit",
        "--jsx", "react-jsx",
        "--target", "esnext",
        "--moduleResolution", "bundler",
        "--allowImportingTsExtensions",
        "--resolveJsonModule",
        "--isolatedModules",
        "--strict",
        "--maxNodeModuleJsDepth", "0",
    ] + files
    return run(cmd, cwd=work_dir, env=env)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = b"OK"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def _json(self, status: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/tsc-static-analysis":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as e:
            self._json(400, {"error": f"invalid json: {e}"})
            return

        files = payload.get("files") or []
        deps = payload.get("dependencies")  # optional

        if not files:
            self._json(400, {"error": "'files' is required and must be non-empty"})
            return

        # Prepare working directory
        run_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
        work_dir = Path(VOLUME_MOUNT_POINT) / "tsc-runs" / run_id
        try:
            work_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self._json(500, {"error": f"failed to create work dir: {e}"})
            return

        env = ensure_bun_cache_env(os.environ.copy())

        try:
            write_files(work_dir, files)
            write_package_json(work_dir, deps)

            bun_ms, bun_out, bun_err, bun_rc = bun_install(work_dir, env)

            file_paths = [f.get("path") for f in files if f.get("path")]
            ts_ms, ts_out, ts_err, ts_rc = run_tsgo(work_dir, file_paths, env)

            self._json(200, {
                "workDir": str(work_dir),
                "bun": {"ms": bun_ms, "returncode": bun_rc, "stdout": bun_out, "stderr": bun_err},
                "tsgo": {"ms": ts_ms, "returncode": ts_rc, "stdout": ts_out, "stderr": ts_err},
            })
        except Exception as e:
            self._json(500, {"error": str(e), "workDir": str(work_dir)})


def main():
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "3000"))

    # Ensure base directories exist
    Path(VOLUME_MOUNT_POINT).mkdir(parents=True, exist_ok=True)
    ensure_bun_cache_env(os.environ.copy())

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"[fast-tsc-server] listening on {host}:{port}, volume={VOLUME_MOUNT_POINT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()


