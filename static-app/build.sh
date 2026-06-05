#!/bin/sh
set -eu

BUILD_ID="${BUILD_ID:-dev-$(date +%s)}"

main_src="window.BUILD_ID=\"$BUILD_ID\";document.getElementById('out').innerText='loaded main from build '+window.BUILD_ID;"
vendor_src="window.VENDOR_BUILD=\"$BUILD_ID\";"

main_hash=$(printf "%s" "$main_src"   | shasum -a 256 | cut -c1-8)
vendor_hash=$(printf "%s" "$vendor_src" | shasum -a 256 | cut -c1-8)

main_file="main-${main_hash}.js"
vendor_file="vendor-${vendor_hash}.js"

rm -rf build
mkdir -p build/assets

printf "%s" "$main_src"   > "build/assets/${main_file}"
printf "%s" "$vendor_src" > "build/assets/${vendor_file}"

cat > build/index.html <<HTML
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>static-app ${BUILD_ID}</title>
</head>
<body>
  <h1>static-app</h1>
  <p>HTML build id: <code>${BUILD_ID}</code></p>
  <p>main chunk: <code>${main_file}</code></p>
  <p>vendor chunk: <code>${vendor_file}</code></p>
  <p id="out">main has not loaded yet</p>
  <button id="refetch">re-fetch main chunk</button>
  <pre id="log"></pre>
  <script src="/assets/${vendor_file}"></script>
  <script src="/assets/${main_file}"></script>
  <script>
    const MAIN_URL = "/assets/${main_file}";
    const log = (m) => {
      const el = document.getElementById('log');
      el.textContent += new Date().toISOString() + '  ' + m + '\\n';
    };
    document.getElementById('refetch').addEventListener('click', async () => {
      try {
        const r = await fetch(MAIN_URL, { cache: 'no-store' });
        log('GET ' + MAIN_URL + ' -> ' + r.status);
      } catch (e) {
        log('GET ' + MAIN_URL + ' -> ERROR ' + e.message);
      }
    });
  </script>
</body>
</html>
HTML

echo "built build/ with BUILD_ID=${BUILD_ID}, main=${main_file}, vendor=${vendor_file}"
