#!/usr/bin/env bash
#
# probe-jobs.sh — seed load for the agent's queue probe controller.
#
#   probe-jobs.sh seed <kubeconfig> <count>   create N suspended probe jobs (no pods, pure objects)
#   probe-jobs.sh marker <kubeconfig>         create one marker job and print its name + creation time
#   probe-jobs.sh cleanup <kubeconfig>        delete the probe namespace and everything in it
#
# Probe jobs carry porter.run/queue-probe=true (watched only by the queue probe controller) and
# never porter.run/porter-application, so the real jobs controller can't see them. Suspended jobs
# create no pods: they exist purely as Job objects for the informer's resync to replay.

set -euo pipefail

command="${1:?usage: probe-jobs.sh seed|marker|cleanup <kubeconfig> [count]}"
kubeconfig="${2:?kubeconfig path required}"
namespace="queue-probe"

ensure_namespace() {
  kubectl --kubeconfig "$kubeconfig" create namespace "$namespace" --dry-run=client -o yaml | \
    kubectl --kubeconfig "$kubeconfig" apply -f - >/dev/null
}

job_manifest() {
  local name="$1" extra_labels="$2"
  cat <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: ${name}
  namespace: ${namespace}
  labels:
    porter.run/queue-probe: "true"
    porter.run/porter-application: "true"${extra_labels}
spec:
  suspend: true
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: main
        image: busybox
        command: ["true"]
EOF
}

case "$command" in
  seed)
    count="${3:?count required}"
    ensure_namespace

    batch_size=250
    created=0
    while [ "$created" -lt "$count" ]; do
      batch_end=$((created + batch_size))
      [ "$batch_end" -gt "$count" ] && batch_end="$count"
      {
        for i in $(seq $((created + 1)) "$batch_end"); do
          printf -- '---\n'
          job_manifest "$(printf 'queue-probe-%05d' "$i")" ""
        done
      } | kubectl --kubeconfig "$kubeconfig" apply -f - >/dev/null
      created="$batch_end"
      echo "created $created/$count" >&2
    done
    ;;
  marker)
    ensure_namespace
    name="queue-probe-marker-$(date +%s)"
    job_manifest "$name" $'\n    porter.run/probe-marker: "true"' | \
      kubectl --kubeconfig "$kubeconfig" apply -f - >/dev/null
    created_at="$(kubectl --kubeconfig "$kubeconfig" get job "$name" -n "$namespace" -o jsonpath='{.metadata.creationTimestamp}')"
    echo "$name created at $created_at"
    ;;
  cleanup)
    kubectl --kubeconfig "$kubeconfig" delete namespace "$namespace" --ignore-not-found
    ;;
  *)
    echo "unknown command: $command" >&2
    exit 1
    ;;
esac
