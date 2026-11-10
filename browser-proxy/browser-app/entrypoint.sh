#!/usr/bin/env bash
#
# Starts the egress proxy and the browser server. As root, each runs as its own
# user: the egress proxy alone can read the upstream proxy credentials, so the
# browser the agent drives cannot.

set -euo pipefail

egress_dir=/run/egress
egress_config="$egress_dir/gost.yaml"

mkdir -p "$egress_dir"
chmod 700 "$egress_dir"
(umask 077 && node /app/egress-config.mjs > "$egress_config")

if [ "$(id -u)" = 0 ]; then
  chown -R egress:egress "$egress_dir"
  as_egress=(setpriv --reuid=egress --regid=egress --init-groups)
  as_browser=(setpriv --reuid=node --regid=node --init-groups)
else
  echo "running as uid $(id -u), not root: the browser shares a user with the egress proxy and can read the upstream credentials" >&2
  as_egress=()
  as_browser=()
fi

(cd "$egress_dir" && exec env -i PATH="$PATH" "${as_egress[@]}" gost -C "$egress_config") &
env -u UPSTREAM_PROXY_URL HOME=/home/node "${as_browser[@]}" node /app/server.mjs &

trap 'kill -TERM $(jobs -p) 2>/dev/null' TERM INT
wait -n
exit 1
