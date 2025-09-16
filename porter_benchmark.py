#!/usr/bin/env python3
import os, sys, json, time, shutil, subprocess, textwrap, tempfile
from pathlib import Path
import re
from datetime import datetime

# ---------- Config ----------
VOLUME_MOUNT_POINT = os.environ.get("VOLUME_MOUNT_POINT", "/tmp/nvme")
APP_DIR = Path(os.environ.get("APP_DIR", f"{VOLUME_MOUNT_POINT}/porter-bench/shadcn-app"))
SRC_DIR = APP_DIR / "src"
EXAMPLE_FILE = SRC_DIR / "LandingPage.tsx"

# Bun caches on the mounted volume
os.environ.setdefault("BUN_INSTALL_CACHE_DIR", f"{VOLUME_MOUNT_POINT}/bun/install")
os.environ.setdefault("BUN_RUNTIME_TRANSPILER_CACHE_PATH", f"{VOLUME_MOUNT_POINT}/bun/transpiler-cache")
os.environ.setdefault("BUN_RUNTIME_CACHE_PATH", f"{VOLUME_MOUNT_POINT}/bun/runtime-cache")

# Benchmark results storage
BENCHMARK_RESULTS = {
    "start_time": None,
    "volume_mount_point": VOLUME_MOUNT_POINT,
    "timings": {},
    "cache_stats": {},
    "volume_info": {}
}

PKGS = [
    "react", "react-dom", "typescript", "vite",
    "lucide-react", "react-router-dom",
    "@types/react", "@types/react-dom"
]

TSGO = os.environ.get("TSGO_PATH") or "/usr/local/bin/tsgo"

BASE_ENV = os.environ.copy()

def run(cmd, cwd=None, check=True, name="", benchmark_key=None):
    """Enhanced run function with detailed timing and benchmark tracking"""
    operation_name = name or " ".join(cmd)
    print(f"[START] {operation_name}")
    
    t0 = time.perf_counter()
    start_time = datetime.now().isoformat()
    
    proc = subprocess.run(
        cmd, cwd=cwd, env=BASE_ENV, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    
    wall_ms = int((time.perf_counter() - t0) * 1000)
    end_time = datetime.now().isoformat()
    
    # Store detailed timing info
    timing_info = {
        "wall_time_ms": wall_ms,
        "start_time": start_time,
        "end_time": end_time,
        "command": " ".join(cmd),
        "cwd": str(cwd) if cwd else None,
        "returncode": proc.returncode,
        "stdout_bytes": len(proc.stdout.encode('utf-8')),
        "stderr_bytes": len(proc.stderr.encode('utf-8'))
    }
    
    if benchmark_key:
        BENCHMARK_RESULTS["timings"][benchmark_key] = timing_info
    
    print(f"[END] {operation_name} - {wall_ms}ms (rc={proc.returncode})")
    
    if check and proc.returncode != 0:
        print("----- STDOUT -----", file=sys.stderr); print(proc.stdout, file=sys.stderr)
        print("----- STDERR -----", file=sys.stderr); print(proc.stderr, file=sys.stderr)
        sys.exit(proc.returncode)
    
    return wall_ms, proc.stdout, proc.stderr, proc.returncode

def ensure_tools():
    missing = []
    if not shutil.which("bun"): missing.append("bun")
    if not os.path.exists(TSGO): missing.append(f"tsgo (expected at {TSGO}, set TSGO_PATH if different)")
    if missing:
        print(f"[fatal] missing tools: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

def collect_volume_info():
    """Collect detailed information about the volume mount point and cache directories"""
    print("=== VOLUME MOUNT ANALYSIS ===")
    
    volume_info = {
        "mount_point": VOLUME_MOUNT_POINT,
        "cache_directories": {},
        "mount_details": {},
        "disk_usage": {}
    }
    
    # Check cache directories
    cache_dirs = {
        "bun_install": os.environ.get("BUN_INSTALL_CACHE_DIR"),
        "bun_transpiler": os.environ.get("BUN_RUNTIME_TRANSPILER_CACHE_PATH"),
        "bun_runtime": os.environ.get("BUN_RUNTIME_CACHE_PATH"),
        "app_dir": str(APP_DIR)
    }
    
    for name, path in cache_dirs.items():
        if path:
            exists = Path(path).exists()
            size = get_dir_size(path) if exists else 0
            volume_info["cache_directories"][name] = {
                "path": path,
                "exists": exists,
                "size_mb": round(size / (1024*1024), 2)
            }
            print(f"  {name}: {path} ({'EXISTS' if exists else 'MISSING'}) - {volume_info['cache_directories'][name]['size_mb']}MB")
    
    # Check mount information
    try:
        with open("/proc/mounts") as f:
            for line in f:
                if VOLUME_MOUNT_POINT in line:
                    parts = line.strip().split()
                    volume_info["mount_details"] = {
                        "device": parts[0],
                        "mountpoint": parts[1],
                        "filesystem": parts[2],
                        "options": parts[3] if len(parts) > 3 else ""
                    }
                    print(f"  Mount: {line.strip()}")
                    break
    except Exception as e:
        print(f"  Mount info unavailable: {e}")
    
    # Disk usage
    try:
        if Path(VOLUME_MOUNT_POINT).exists():
            stat = shutil.disk_usage(VOLUME_MOUNT_POINT)
            volume_info["disk_usage"] = {
                "total_gb": round(stat.total / (1024**3), 2),
                "used_gb": round((stat.total - stat.free) / (1024**3), 2),
                "free_gb": round(stat.free / (1024**3), 2)
            }
            print(f"  Disk: {volume_info['disk_usage']['used_gb']:.2f}GB used / {volume_info['disk_usage']['total_gb']:.2f}GB total")
    except Exception as e:
        print(f"  Disk usage unavailable: {e}")
    
    BENCHMARK_RESULTS["volume_info"] = volume_info
    print("=============================")
    return volume_info

def get_dir_size(path):
    """Get directory size in bytes"""
    try:
        total = 0
        for entry in Path(path).rglob('*'):
            if entry.is_file():
                total += entry.stat().st_size
        return total
    except Exception:
        return 0

def scaffold_project():
    if APP_DIR.exists() and (APP_DIR / "package.json").exists():
        print(f"[ok] Project exists: {APP_DIR}")
        return

    if APP_DIR.exists():
        shutil.rmtree(APP_DIR)
    APP_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[init] Scaffolding in {APP_DIR}")
    wall, out, err, rc = run(["bun", "init", "--react=shadcn", "-y"], cwd=str(APP_DIR), check=False, 
                           name="bun init shadcn", benchmark_key="scaffold_init")
    if rc != 0:
        print("[warn] `bun init --react=shadcn` failed; falling back to vite react-ts")
        run(["bun", "create", "vite", ".", "--template", "react-ts"], cwd=str(APP_DIR), 
            name="bun create vite", benchmark_key="scaffold_fallback")

    tsconfig = APP_DIR / "tsconfig.json"
    if not tsconfig.exists():
        tsconfig.write_text(json.dumps({
            "compilerOptions": {
                "target": "ES2022",
                "module": "esnext",
                "strict": True,
                "jsx": "react-jsx",
                "moduleResolution": "bundler",
                "allowJs": True,
                "skipLibCheck": True
            },
            "include": ["src/**/*"]
        }, indent=2))

def write_sample_file():
    SRC_DIR.mkdir(parents=True, exist_ok=True)

    body = textwrap.dedent("""\
        // Import icons from lucide-react
        import { HomeIcon, DownloadIcon, SettingsIcon, UserIcon, LogOutIcon } from "lucide-react";
        // Import react-router-dom
        import { Link, useNavigate } from "react-router-dom";
        // Import React
        import React from "react";

        const TrivialExample: React.FC = () => {

          const someFunction = () => {
            console.log('isabella's trivial example');
          };

          return (
            <div className="min-h-screen bg-gray-100">
              <h1>Landing Page</h1>
              <button type="button" onClick={someFunction}>Click me</button>
            </div>
          );
        };

        export default TrivialExample;
    """)
    EXAMPLE_FILE.write_text(body)
    print(f"[ok] Wrote {EXAMPLE_FILE}")

def ensure_package_json_scripts():
    pkg = APP_DIR / "package.json"
    try:
        data = json.loads(pkg.read_text())
    except Exception:
        data = {}
    data.setdefault("scripts", {})
    data["scripts"].setdefault("build", f"{TSGO} --noEmit")
    pkg.write_text(json.dumps(data, indent=2))

def bun_install_min_deps():
    """Install bun dependencies with detailed timing and cache analysis"""
    print("=== BUN INSTALL BENCHMARK ===")
    
    # Capture cache state before install
    cache_before = {}
    for name, info in BENCHMARK_RESULTS["volume_info"]["cache_directories"].items():
        if info["exists"]:
            cache_before[name] = get_dir_size(info["path"])
    
    print("[DEPS] bun install (baseline)")
    wall_ms, stdout, stderr, rc = run(
        ["bun", "install", "--ignore-scripts", "--silent", "--no-progress", "--no-summary", "--no-verify", "--backend=hardlink"], 
        cwd=str(APP_DIR), name="bun install baseline", benchmark_key="bun_install_baseline"
    )
    
    # Capture cache state after baseline install
    cache_after_baseline = {}
    for name, info in BENCHMARK_RESULTS["volume_info"]["cache_directories"].items():
        if Path(info["path"]).exists():
            cache_after_baseline[name] = get_dir_size(info["path"])
    
    print("[DEPS] bun add (package dependencies)")
    wall_ms_add, stdout_add, stderr_add, rc_add = run(
        ["bun", "add", "--ignore-scripts", "--silent", "--no-progress", "--no-summary", "--no-verify",
         "--backend=hardlink", "--no-save", *PKGS], 
        cwd=str(APP_DIR), name="bun add deps", benchmark_key="bun_add_packages"
    )
    
    # Capture final cache state
    cache_after_add = {}
    for name, info in BENCHMARK_RESULTS["volume_info"]["cache_directories"].items():
        if Path(info["path"]).exists():
            cache_after_add[name] = get_dir_size(info["path"])
    
    # Calculate cache growth
    cache_stats = {
        "before_install_mb": {k: round(v/(1024*1024), 2) for k, v in cache_before.items()},
        "after_baseline_mb": {k: round(v/(1024*1024), 2) for k, v in cache_after_baseline.items()},
        "after_packages_mb": {k: round(v/(1024*1024), 2) for k, v in cache_after_add.items()},
        "growth_baseline_mb": {},
        "growth_packages_mb": {},
        "total_growth_mb": {}
    }
    
    # Calculate growth deltas
    for cache_name in cache_before.keys():
        baseline_growth = (cache_after_baseline.get(cache_name, 0) - cache_before.get(cache_name, 0)) / (1024*1024)
        packages_growth = (cache_after_add.get(cache_name, 0) - cache_after_baseline.get(cache_name, 0)) / (1024*1024)
        total_growth = (cache_after_add.get(cache_name, 0) - cache_before.get(cache_name, 0)) / (1024*1024)
        
        cache_stats["growth_baseline_mb"][cache_name] = round(baseline_growth, 2)
        cache_stats["growth_packages_mb"][cache_name] = round(packages_growth, 2)
        cache_stats["total_growth_mb"][cache_name] = round(total_growth, 2)
    
    BENCHMARK_RESULTS["cache_stats"] = cache_stats
    
    # Print detailed results
    print(f"\n=== BUN INSTALL RESULTS ===")
    print(f"Baseline install: {wall_ms}ms")
    print(f"Package add: {wall_ms_add}ms") 
    print(f"Total install time: {wall_ms + wall_ms_add}ms")
    
    print(f"\n=== CACHE GROWTH ANALYSIS ===")
    for cache_name in cache_before.keys():
        print(f"{cache_name}:")
        print(f"  Before: {cache_stats['before_install_mb'][cache_name]}MB")
        print(f"  After baseline: {cache_stats['after_baseline_mb'][cache_name]}MB (+{cache_stats['growth_baseline_mb'][cache_name]}MB)")
        print(f"  After packages: {cache_stats['after_packages_mb'][cache_name]}MB (+{cache_stats['growth_packages_mb'][cache_name]}MB)")
        print(f"  Total growth: +{cache_stats['total_growth_mb'][cache_name]}MB")
    
    print("==============================")

def benchmark_symlink_operations():
    """Benchmark symlink creation/deletion performance - critical for node_modules handling"""
    print("=== SYMLINK PERFORMANCE BENCHMARK ===")
    
    # Create test directory structure for symlinking
    test_dir = Path(VOLUME_MOUNT_POINT) / "symlink-test"
    source_dir = test_dir / "source"
    target_dir = test_dir / "target"
    
    # Setup
    setup_start = time.perf_counter()
    test_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(exist_ok=True)
    target_dir.mkdir(exist_ok=True)
    
    # Create fake node_modules structure
    node_modules_src = source_dir / "node_modules"
    node_modules_src.mkdir(exist_ok=True)
    
    # Create some dummy files to simulate a real node_modules
    for i in range(100):
        dummy_file = node_modules_src / f"package_{i}" / "index.js"
        dummy_file.parent.mkdir(exist_ok=True)
        dummy_file.write_text(f"// Dummy package {i}")
    
    setup_ms = int((time.perf_counter() - setup_start) * 1000)
    
    # Benchmark symlink creation
    symlink_start = time.perf_counter()
    node_modules_link = target_dir / "node_modules"
    if node_modules_link.exists():
        if node_modules_link.is_symlink():
            node_modules_link.unlink()
        else:
            shutil.rmtree(node_modules_link)
    
    os.symlink(node_modules_src, node_modules_link)
    symlink_create_ms = int((time.perf_counter() - symlink_start) * 1000)
    
    # Test symlink access performance
    access_start = time.perf_counter()
    link_files = list(node_modules_link.rglob("*.js"))
    access_ms = int((time.perf_counter() - access_start) * 1000)
    
    # Benchmark symlink deletion
    delete_start = time.perf_counter()
    node_modules_link.unlink()
    delete_ms = int((time.perf_counter() - delete_start) * 1000)
    
    # Cleanup
    cleanup_start = time.perf_counter()
    shutil.rmtree(test_dir)
    cleanup_ms = int((time.perf_counter() - cleanup_start) * 1000)
    
    # Store results
    symlink_stats = {
        "setup_ms": setup_ms,
        "symlink_create_ms": symlink_create_ms,
        "symlink_access_ms": access_ms,
        "symlink_delete_ms": delete_ms,
        "cleanup_ms": cleanup_ms,
        "files_accessed": len(link_files),
        "total_symlink_ops_ms": symlink_create_ms + access_ms + delete_ms
    }
    
    BENCHMARK_RESULTS["timings"]["symlink_operations"] = {
        "wall_time_ms": symlink_stats["total_symlink_ops_ms"],
        "operation": "Symlink create/access/delete benchmark",
        "details": symlink_stats
    }
    
    print(f"Setup: {setup_ms}ms")
    print(f"Symlink creation: {symlink_create_ms}ms")
    print(f"Symlink access ({len(link_files)} files): {access_ms}ms")
    print(f"Symlink deletion: {delete_ms}ms")
    print(f"Cleanup: {cleanup_ms}ms")
    print(f"Total symlink operations: {symlink_stats['total_symlink_ops_ms']}ms")
    print("======================================")

def benchmark_temp_dir_operations():
    """Benchmark temp directory creation/deletion - mirrors src/utils/fs.py create_temp_dir()"""
    print("=== TEMP DIRECTORY BENCHMARK ===")
    
    temp_parent_dir = f"{VOLUME_MOUNT_POINT}/temp"
    
    # Test directory creation performance
    create_start = time.perf_counter()
    Path(temp_parent_dir).mkdir(parents=True, exist_ok=True)
    
    # Create multiple temp directories like the real code does
    temp_dirs = []
    for i in range(10):
        temp_dir = tempfile.mkdtemp(prefix=f"benchmark-temp-{i}-", dir=temp_parent_dir)
        temp_dirs.append(temp_dir)
    
    create_ms = int((time.perf_counter() - create_start) * 1000)
    
    # Test file creation within temp directories
    file_ops_start = time.perf_counter()
    total_files = 0
    for temp_dir in temp_dirs:
        # Create some files in each temp dir
        for j in range(20):
            test_file = Path(temp_dir) / f"test_{j}.tsx"
            test_file.write_text(f"// Test file {j} in {Path(temp_dir).name}")
            total_files += 1
    
    file_ops_ms = int((time.perf_counter() - file_ops_start) * 1000)
    
    # Test cleanup performance
    cleanup_start = time.perf_counter()
    for temp_dir in temp_dirs:
        shutil.rmtree(temp_dir)
    cleanup_ms = int((time.perf_counter() - cleanup_start) * 1000)
    
    temp_stats = {
        "temp_dirs_created": len(temp_dirs),
        "create_ms": create_ms,
        "file_operations_ms": file_ops_ms,
        "total_files_created": total_files,
        "cleanup_ms": cleanup_ms,
        "total_temp_ops_ms": create_ms + file_ops_ms + cleanup_ms
    }
    
    BENCHMARK_RESULTS["timings"]["temp_dir_operations"] = {
        "wall_time_ms": temp_stats["total_temp_ops_ms"],
        "operation": "Temp directory create/populate/cleanup",
        "details": temp_stats
    }
    
    print(f"Created {len(temp_dirs)} temp directories: {create_ms}ms")
    print(f"File operations ({total_files} files): {file_ops_ms}ms") 
    print(f"Cleanup: {cleanup_ms}ms")
    print(f"Total temp directory operations: {temp_stats['total_temp_ops_ms']}ms")
    print("=================================")

def benchmark_rsync_operations():
    """Benchmark rsync performance - critical operation from src/utils/fs.py"""
    print("=== RSYNC PERFORMANCE BENCHMARK ===")
    
    # Create source directory structure
    rsync_test_dir = Path(VOLUME_MOUNT_POINT) / "rsync-test"
    source_dir = rsync_test_dir / "source"
    target_dir = rsync_test_dir / "target"
    
    # Setup source directory with nested structure
    setup_start = time.perf_counter()
    source_dir.mkdir(parents=True, exist_ok=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Create realistic project structure
    (source_dir / "src" / "components").mkdir(parents=True, exist_ok=True)
    (source_dir / "src" / "utils").mkdir(parents=True, exist_ok=True)
    (source_dir / "node_modules" / "react" / "lib").mkdir(parents=True, exist_ok=True)
    
    # Create files
    files_created = 0
    for subdir in ["src/components", "src/utils"]:
        for i in range(50):
            file_path = source_dir / subdir / f"Component{i}.tsx"
            file_path.write_text(f"// Component {i}\nimport React from 'react';\nexport default function Component{i}() {{ return <div>Test</div>; }}")
            files_created += 1
    
    # Create node_modules files (to be excluded)
    for i in range(20):
        nm_file = source_dir / "node_modules" / "react" / "lib" / f"file{i}.js"
        nm_file.write_text(f"// React file {i}")
        files_created += 1
    
    setup_ms = int((time.perf_counter() - setup_start) * 1000)
    
    # Benchmark rsync with exclusions (mirrors real code)
    rsync_start = time.perf_counter()
    result = subprocess.run([
        "rsync", "-av",
        "--exclude=**/node_modules/",
        "--exclude=.git",
        str(source_dir),
        str(target_dir)
    ], capture_output=True, text=True)
    rsync_ms = int((time.perf_counter() - rsync_start) * 1000)
    
    # Count copied files
    copied_files = len(list((target_dir / source_dir.name).rglob("*"))) - len(list((target_dir / source_dir.name).rglob("**/node_modules")))
    
    # Cleanup
    cleanup_start = time.perf_counter()
    shutil.rmtree(rsync_test_dir)
    cleanup_ms = int((time.perf_counter() - cleanup_start) * 1000)
    
    rsync_stats = {
        "setup_ms": setup_ms,
        "rsync_ms": rsync_ms,
        "cleanup_ms": cleanup_ms,
        "source_files_created": files_created,
        "files_copied": copied_files,
        "rsync_returncode": result.returncode,
        "total_rsync_ops_ms": setup_ms + rsync_ms + cleanup_ms
    }
    
    BENCHMARK_RESULTS["timings"]["rsync_operations"] = {
        "wall_time_ms": rsync_stats["total_rsync_ops_ms"],
        "operation": "Rsync directory copy with exclusions",
        "details": rsync_stats
    }
    
    print(f"Setup ({files_created} files): {setup_ms}ms")
    print(f"Rsync operation: {rsync_ms}ms (rc={result.returncode})")
    print(f"Files copied: {copied_files}")
    print(f"Cleanup: {cleanup_ms}ms")
    print(f"Total rsync operations: {rsync_stats['total_rsync_ops_ms']}ms")
    print("====================================")

def benchmark_template_symlink_tsgo():
    """Benchmark the critical path: template with symlinked node_modules -> TSGO compilation"""
    print("=== TEMPLATE + SYMLINK + TSGO BENCHMARK ===")
    
    # Create template structure (mirrors src/utils/fs.py workflow)
    template_test_dir = Path(VOLUME_MOUNT_POINT) / "template-symlink-test"
    template_dir = template_test_dir / "shadcn-template"
    temp_instance_dir = template_test_dir / "temp-instance"
    
    setup_start = time.perf_counter()
    
    # 1. Create "template" with node_modules
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "src" / "components").mkdir(parents=True, exist_ok=True)
    template_node_modules = template_dir / "node_modules"
    template_node_modules.mkdir(exist_ok=True)
    
    # Simulate realistic node_modules structure
    packages = ["react", "react-dom", "typescript", "@types/react", "lucide-react"]
    for pkg in packages:
        pkg_dir = template_node_modules / pkg
        pkg_dir.mkdir(parents=True, exist_ok=True)  # Use parents=True for scoped packages
        (pkg_dir / "index.d.ts").write_text(f"// {pkg} type definitions")
        (pkg_dir / "package.json").write_text(f'{{"name": "{pkg}", "version": "18.0.0"}}')
        # Create nested files to test symlink traversal
        (pkg_dir / "lib" / "index.js").parent.mkdir(exist_ok=True)
        (pkg_dir / "lib" / "index.js").write_text(f"// {pkg} library")
    
    # Create TypeScript files in template
    template_files = [
        ("src/App.tsx", """
import React from 'react';
import { HomeIcon } from 'lucide-react';

export default function App() {
    return <div><HomeIcon /></div>;
}
        """),
        ("src/components/Button.tsx", """
import React from 'react';

interface ButtonProps {
    children: React.ReactNode;
}

export function Button({ children }: ButtonProps) {
    return <button>{children}</button>;
}
        """)
    ]
    
    for file_path, content in template_files:
        full_path = template_dir / file_path
        full_path.write_text(content.strip())
    
    setup_ms = int((time.perf_counter() - setup_start) * 1000)
    
    # 2. Rsync template (excluding node_modules) to temp instance
    rsync_start = time.perf_counter()
    temp_instance_dir.mkdir(parents=True, exist_ok=True)
    
    subprocess.run([
        "rsync", "-av",
        "--exclude=**/node_modules/",
        "--exclude=.git",
        str(template_dir) + "/",  # Note: trailing slash copies contents
        str(temp_instance_dir)
    ], capture_output=True, text=True, check=True)
    rsync_ms = int((time.perf_counter() - rsync_start) * 1000)
    
    # 3. Create symlink from temp instance to template's node_modules
    symlink_start = time.perf_counter()
    instance_node_modules = temp_instance_dir / "node_modules"
    os.symlink(template_node_modules, instance_node_modules)
    symlink_ms = int((time.perf_counter() - symlink_start) * 1000)
    
    # 4. Run TSGO on the temp instance (critical: TSGO must follow symlinks)
    tsgo_start = time.perf_counter()
    tsgo_cmd = [
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
        "src/App.tsx",
        "src/components/Button.tsx"
    ]
    
    tsgo_result = subprocess.run(
        tsgo_cmd, cwd=str(temp_instance_dir), 
        capture_output=True, text=True
    )
    tsgo_ms = int((time.perf_counter() - tsgo_start) * 1000)
    
    # Count how many files TSGO had to access through symlinks
    symlinked_files_count = len(list(instance_node_modules.rglob("*"))) if instance_node_modules.exists() else 0
    
    # Cleanup
    cleanup_start = time.perf_counter()
    shutil.rmtree(template_test_dir)
    cleanup_ms = int((time.perf_counter() - cleanup_start) * 1000)
    
    # Calculate total workflow time
    total_workflow_ms = setup_ms + rsync_ms + symlink_ms + tsgo_ms
    
    template_symlink_stats = {
        "setup_ms": setup_ms,
        "rsync_template_ms": rsync_ms,
        "symlink_creation_ms": symlink_ms,
        "tsgo_compilation_ms": tsgo_ms,
        "cleanup_ms": cleanup_ms,
        "total_workflow_ms": total_workflow_ms,
        "tsgo_returncode": tsgo_result.returncode,
        "symlinked_files_count": symlinked_files_count,
        "packages_symlinked": len(packages)
    }
    
    BENCHMARK_RESULTS["timings"]["template_symlink_tsgo_workflow"] = {
        "wall_time_ms": total_workflow_ms,
        "operation": "Template rsync + symlink + TSGO compilation workflow",
        "details": template_symlink_stats
    }
    
    print(f"Template setup ({len(packages)} packages): {setup_ms}ms")
    print(f"Rsync template: {rsync_ms}ms")
    print(f"Symlink node_modules: {symlink_ms}ms")
    print(f"TSGO compilation (following symlinks): {tsgo_ms}ms (rc={tsgo_result.returncode})")
    print(f"Symlinked files accessed: {symlinked_files_count}")
    print(f"Total workflow time: {total_workflow_ms}ms")
    print(f"Cleanup: {cleanup_ms}ms")
    
    if tsgo_result.returncode != 0:
        print(f"TSGO stderr: {tsgo_result.stderr}")
    
    print("===========================================")

def benchmark_concurrent_file_operations():
    """Test concurrent file I/O performance - critical for bun/npm parallel operations"""
    print("=== CONCURRENT FILE OPERATIONS BENCHMARK ===")
    import concurrent.futures
    
    concurrent_test_dir = Path(VOLUME_MOUNT_POINT) / "concurrent-test"
    concurrent_test_dir.mkdir(parents=True, exist_ok=True)
    
    # Test 1: Sequential file writes
    print("Testing sequential file operations...")
    sequential_start = time.perf_counter()
    for i in range(100):
        test_file = concurrent_test_dir / f"sequential_{i}.js"
        test_file.write_text(f"// Sequential file {i}\nconst value = {i};\nmodule.exports = {{ value }};")
    sequential_ms = int((time.perf_counter() - sequential_start) * 1000)
    
    # Test 2: Concurrent file writes using threading
    def write_concurrent_file(file_id):
        test_file = concurrent_test_dir / f"concurrent_{file_id}.js"
        test_file.write_text(f"// Concurrent file {file_id}\nconst value = {file_id};\nmodule.exports = {{ value }};")
        return file_id
    
    print("Testing concurrent file operations (10 threads)...")
    concurrent_start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(write_concurrent_file, i) for i in range(100)]
        concurrent.futures.wait(futures)
    concurrent_ms = int((time.perf_counter() - concurrent_start) * 1000)
    
    # Test 3: Mixed read/write operations
    print("Testing mixed read/write operations...")
    mixed_start = time.perf_counter()
    
    def mixed_operation(file_id):
        # Write, then immediately read back
        test_file = concurrent_test_dir / f"mixed_{file_id}.js"
        content = f"// Mixed operation {file_id}\nconst data = {file_id * 2};"
        test_file.write_text(content)
        read_content = test_file.read_text()
        return len(read_content)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(mixed_operation, i) for i in range(50)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    mixed_ms = int((time.perf_counter() - mixed_start) * 1000)
    
    # Cleanup and measure
    cleanup_start = time.perf_counter()
    shutil.rmtree(concurrent_test_dir)
    cleanup_ms = int((time.perf_counter() - cleanup_start) * 1000)
    
    concurrent_stats = {
        "sequential_write_ms": sequential_ms,
        "concurrent_write_ms": concurrent_ms,
        "mixed_operations_ms": mixed_ms,
        "cleanup_ms": cleanup_ms,
        "speedup_ratio": round(sequential_ms / concurrent_ms, 2) if concurrent_ms > 0 else 0,
        "files_processed": {
            "sequential": 100,
            "concurrent": 100,
            "mixed": 50
        }
    }
    
    BENCHMARK_RESULTS["timings"]["concurrent_file_operations"] = {
        "wall_time_ms": sequential_ms + concurrent_ms + mixed_ms,
        "operation": "Sequential vs concurrent file I/O benchmark",
        "details": concurrent_stats
    }
    
    print(f"Sequential writes (100 files): {sequential_ms}ms")
    print(f"Concurrent writes (100 files, 10 threads): {concurrent_ms}ms")
    print(f"Mixed read/write (50 files, 8 threads): {mixed_ms}ms")
    print(f"Speedup ratio (sequential/concurrent): {concurrent_stats['speedup_ratio']}x")
    print(f"Cleanup: {cleanup_ms}ms")
    print("============================================")

def benchmark_large_file_operations():
    """Test large file performance - bundles, lockfiles, caches"""
    print("=== LARGE FILE OPERATIONS BENCHMARK ===")
    
    large_file_test_dir = Path(VOLUME_MOUNT_POINT) / "large-file-test"
    large_file_test_dir.mkdir(parents=True, exist_ok=True)
    
    # Test different file sizes
    test_sizes = [
        (1024 * 1024, "1MB"),        # Small bundle
        (10 * 1024 * 1024, "10MB"), # Medium bundle
        (50 * 1024 * 1024, "50MB")  # Large bundle
    ]
    
    large_file_stats = {}
    
    for size_bytes, size_name in test_sizes:
        print(f"Testing {size_name} file operations...")
        
        # Generate test content
        content = "// Large file content\n" * (size_bytes // 20)  # Approximate size
        actual_size = len(content.encode('utf-8'))
        
        test_file = large_file_test_dir / f"large_file_{size_name}.js"
        
        # Test 1: Write large file
        write_start = time.perf_counter()
        test_file.write_text(content)
        write_ms = int((time.perf_counter() - write_start) * 1000)
        
        # Test 2: Read large file
        read_start = time.perf_counter()
        read_content = test_file.read_text()
        read_ms = int((time.perf_counter() - read_start) * 1000)
        
        # Test 3: Copy large file
        copy_start = time.perf_counter()
        copy_file = large_file_test_dir / f"copy_{size_name}.js"
        shutil.copy2(test_file, copy_file)
        copy_ms = int((time.perf_counter() - copy_start) * 1000)
        
        # Calculate throughput
        write_mbps = round((actual_size / (1024*1024)) / (write_ms / 1000), 2) if write_ms > 0 else 0
        read_mbps = round((actual_size / (1024*1024)) / (read_ms / 1000), 2) if read_ms > 0 else 0
        copy_mbps = round((actual_size / (1024*1024)) / (copy_ms / 1000), 2) if copy_ms > 0 else 0
        
        large_file_stats[size_name] = {
            "actual_size_mb": round(actual_size / (1024*1024), 2),
            "write_ms": write_ms,
            "read_ms": read_ms,
            "copy_ms": copy_ms,
            "write_mbps": write_mbps,
            "read_mbps": read_mbps,
            "copy_mbps": copy_mbps
        }
        
        print(f"  {size_name}: Write {write_ms}ms ({write_mbps} MB/s), Read {read_ms}ms ({read_mbps} MB/s), Copy {copy_ms}ms ({copy_mbps} MB/s)")
    
    # Cleanup
    cleanup_start = time.perf_counter()
    shutil.rmtree(large_file_test_dir)
    cleanup_ms = int((time.perf_counter() - cleanup_start) * 1000)
    
    total_time_ms = sum(stats["write_ms"] + stats["read_ms"] + stats["copy_ms"] for stats in large_file_stats.values())
    
    BENCHMARK_RESULTS["timings"]["large_file_operations"] = {
        "wall_time_ms": total_time_ms,
        "operation": "Large file write/read/copy benchmark",
        "details": {
            "file_tests": large_file_stats,
            "cleanup_ms": cleanup_ms
        }
    }
    
    print(f"Cleanup: {cleanup_ms}ms")
    print("=======================================")

def benchmark_bun_cache_performance():
    """Test bun install with empty vs populated cache - critical for volume performance"""
    print("=== BUN CACHE PERFORMANCE BENCHMARK ===")
    
    # Create a test project for cache testing
    cache_test_dir = Path(VOLUME_MOUNT_POINT) / "bun-cache-test"
    cache_test_dir.mkdir(parents=True, exist_ok=True)
    
    # Create separate test cache directories for isolation
    empty_cache_dir = Path(VOLUME_MOUNT_POINT) / "bun-cache-empty"
    populated_cache_dir = Path(VOLUME_MOUNT_POINT) / "bun-cache-populated"
    
    # Create package.json with several packages to install
    package_json = {
        "name": "cache-test",
        "version": "1.0.0",
        "dependencies": {
            "react": "^18.0.0",
            "react-dom": "^18.0.0", 
            "typescript": "^5.0.0",
            "lodash": "^4.17.21",
            "@types/react": "^18.0.0"
        }
    }
    
    package_json_file = cache_test_dir / "package.json"
    package_json_file.write_text(json.dumps(package_json, indent=2))
    
    # Test with EMPTY cache first
    print("Phase 1: Testing with EMPTY bun cache...")
    
    # Create fresh empty cache directory
    if empty_cache_dir.exists():
        shutil.rmtree(empty_cache_dir)
    empty_cache_dir.mkdir(parents=True, exist_ok=True)
    
    cache_size_before = get_dir_size(str(empty_cache_dir))
    
    # Set up environment for empty cache test
    empty_cache_env = BASE_ENV.copy()
    empty_cache_env["BUN_INSTALL_CACHE_DIR"] = str(empty_cache_dir)
    
    # First install (empty cache)
    empty_cache_start = time.perf_counter()
    result_empty = subprocess.run([
        "bun", "install", 
        "--ignore-scripts", "--silent", "--no-progress", "--no-summary", 
        "--no-verify", "--backend=hardlink"
    ], cwd=str(cache_test_dir), env=empty_cache_env, capture_output=True, text=True)
    empty_cache_ms = int((time.perf_counter() - empty_cache_start) * 1000)
    
    cache_size_after_first = get_dir_size(str(empty_cache_dir))
    
    print("Phase 2: Testing with POPULATED cache...")
    
    # Copy populated cache from the first install
    if populated_cache_dir.exists():
        shutil.rmtree(populated_cache_dir)
    shutil.copytree(empty_cache_dir, populated_cache_dir)
    
    # Remove node_modules but keep cache
    node_modules = cache_test_dir / "node_modules"
    if node_modules.exists():
        shutil.rmtree(node_modules)
    
    # Set up environment for populated cache test
    populated_cache_env = BASE_ENV.copy()
    populated_cache_env["BUN_INSTALL_CACHE_DIR"] = str(populated_cache_dir)
    
    # Second install (populated cache)
    populated_cache_start = time.perf_counter()
    result_populated = subprocess.run([
        "bun", "install",
        "--ignore-scripts", "--silent", "--no-progress", "--no-summary",
        "--no-verify", "--backend=hardlink"  
    ], cwd=str(cache_test_dir), env=populated_cache_env, capture_output=True, text=True)
    populated_cache_ms = int((time.perf_counter() - populated_cache_start) * 1000)
    
    cache_size_final = get_dir_size(str(populated_cache_dir))
    
    # Calculate stats
    cache_speedup = round(empty_cache_ms / populated_cache_ms, 2) if populated_cache_ms > 0 else 0
    cache_growth_mb = round((cache_size_after_first - cache_size_before) / (1024*1024), 2)
    
    bun_cache_stats = {
        "empty_cache_ms": empty_cache_ms,
        "populated_cache_ms": populated_cache_ms,
        "speedup_ratio": cache_speedup,
        "cache_size_before_mb": round(cache_size_before / (1024*1024), 2),
        "cache_size_after_first_mb": round(cache_size_after_first / (1024*1024), 2),
        "cache_size_final_mb": round(cache_size_final / (1024*1024), 2),
        "cache_growth_mb": cache_growth_mb,
        "packages_installed": len(package_json["dependencies"])
    }
    
    BENCHMARK_RESULTS["timings"]["bun_cache_performance"] = {
        "wall_time_ms": empty_cache_ms + populated_cache_ms,
        "operation": "Bun install empty vs populated cache",
        "details": bun_cache_stats
    }
    
    # Cleanup test directories
    cleanup_start = time.perf_counter()
    shutil.rmtree(cache_test_dir)
    shutil.rmtree(empty_cache_dir)
    shutil.rmtree(populated_cache_dir)
    cleanup_ms = int((time.perf_counter() - cleanup_start) * 1000)
    
    print(f"Empty cache install: {empty_cache_ms}ms")
    print(f"Populated cache install: {populated_cache_ms}ms")
    print(f"Cache speedup: {cache_speedup}x faster with populated cache")
    print(f"Cache growth: {cache_growth_mb}MB")
    print(f"Packages installed: {len(package_json['dependencies'])}")
    print(f"Cleanup: {cleanup_ms}ms")
    print("=======================================")

def benchmark_file_intensive_operations():
    """Run all file-intensive benchmarks that are sensitive to volume mount performance"""
    print("\n=== FILE-INTENSIVE OPERATIONS BENCHMARK ===")
    benchmark_symlink_operations()
    benchmark_temp_dir_operations() 
    benchmark_rsync_operations()
    benchmark_concurrent_file_operations()  # New!
    benchmark_large_file_operations()       # New!
    benchmark_template_symlink_tsgo()       # The critical path!
    benchmark_bun_cache_performance()       # Cache performance test!
    print("============================================")

def run_tsgo():
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
        "--strictNullChecks",
        "--strict",
        "--maxNodeModuleJsDepth", "0",
        str(EXAMPLE_FILE),
    ]
    print(f"[TSGO] {' '.join(cmd)}")
    wall_ms, out, err, _ = run(cmd, cwd=str(APP_DIR), name="tsgo typecheck", benchmark_key="tsgo_typecheck")
    return wall_ms, out, err

def summarize_ts_errors(stdout_text: str):
    codes = {}
    per_file = {}
    for line in stdout_text.splitlines():
        m = re.search(r"error (TS\d+)", line)
        if m:
            code = m.group(1)
            codes[code] = codes.get(code, 0) + 1
            # Extract filename
            mf = re.match(r"^(.*?\.(?:ts|tsx|js|jsx))\((\d+),(\d+)\):", line.strip())
            if mf:
                f = mf.group(1)
                per_file.setdefault(f, {})
                per_file[f][code] = per_file[f].get(code, 0) + 1

    if not codes:
        print("[diag] No TS errors detected 🎉")
        return

    print("\n[diag] Error counts by code:")
    for k in sorted(codes.keys()):
        print(f"  {k}: {codes[k]}")

    print("\n[diag] Errors per file:")
    for f, d in per_file.items():
        pretty = ", ".join(f"{k}:{v}" for k, v in sorted(d.items()))
        print(f"  {f}: {pretty}")

def save_benchmark_results():
    """Save benchmark results to JSON file"""
    BENCHMARK_RESULTS["end_time"] = datetime.now().isoformat()
    
    # Calculate total benchmark time
    if BENCHMARK_RESULTS["start_time"]:
        start = datetime.fromisoformat(BENCHMARK_RESULTS["start_time"])
        end = datetime.fromisoformat(BENCHMARK_RESULTS["end_time"])
        total_ms = int((end - start).total_seconds() * 1000)
        BENCHMARK_RESULTS["total_benchmark_time_ms"] = total_ms
    
    # Create benchmark results file
    results_file = Path(VOLUME_MOUNT_POINT) / "porter_benchmark_results.json"
    results_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(results_file, 'w') as f:
        json.dump(BENCHMARK_RESULTS, f, indent=2)
    
    print(f"\n=== BENCHMARK SUMMARY ===")
    print(f"Results saved to: {results_file}")
    print(f"Total benchmark time: {BENCHMARK_RESULTS.get('total_benchmark_time_ms', 0)}ms")
    print(f"Volume mount point: {VOLUME_MOUNT_POINT}")
    
    # Print timing summary
    if BENCHMARK_RESULTS["timings"]:
        print("\nKey operation timings:")
        for key, timing in BENCHMARK_RESULTS["timings"].items():
            print(f"  {key}: {timing['wall_time_ms']}ms")
    
    print("=========================")

def main():
    BENCHMARK_RESULTS["start_time"] = datetime.now().isoformat()
    print(f"=== PORTER VOLUME MOUNT BENCHMARK ===")
    print(f"Start time: {BENCHMARK_RESULTS['start_time']}")
    print(f"Volume mount point: {VOLUME_MOUNT_POINT}")
    print("=====================================")
    
    ensure_tools()
    collect_volume_info()

    # Create required directories
    print("\n=== DIRECTORY SETUP ===")
    setup_start = time.perf_counter()
    for p in [
        VOLUME_MOUNT_POINT,
        os.environ["BUN_INSTALL_CACHE_DIR"],
        os.environ["BUN_RUNTIME_TRANSPILER_CACHE_PATH"],
        os.environ["BUN_RUNTIME_CACHE_PATH"],
        APP_DIR
    ]:
        Path(p).mkdir(parents=True, exist_ok=True)
        print(f"  Created: {p}")
    
    setup_ms = int((time.perf_counter() - setup_start) * 1000)
    BENCHMARK_RESULTS["timings"]["directory_setup"] = {
        "wall_time_ms": setup_ms,
        "operation": "Create volume mount directories"
    }
    print(f"Directory setup completed: {setup_ms}ms")
    print("=======================")

    # Run benchmark phases
    scaffold_project()
    write_sample_file()
    ensure_package_json_scripts()
    
    # Run file-intensive operations benchmark
    benchmark_file_intensive_operations()
    
    bun_install_min_deps()

    wall_ms, out, err = run_tsgo()
    print(f"\n=== TYPESCRIPT COMPILATION ===")
    print(f"TSGO wall time: {wall_ms}ms")
    print(f"Stdout: {len(out)} bytes")
    print(f"Stderr: {len(err)} bytes")
    
    if err.strip():
        print("\n[TSGO:stderr]")
        print(err)

    if out.strip():
        print("\n[TSGO:stdout] (first 80 lines)")
        lines = out.splitlines()
        print("\n".join(lines[:80]))
        if len(lines) > 80:
            print(f"... ({len(lines)-80} more lines)")

    summarize_ts_errors(out)
    print("===============================")
    
    save_benchmark_results()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr); sys.exit(130)
    except Exception as e:
        print(f"[fatal] {e}", file=sys.stderr); sys.exit(1)
