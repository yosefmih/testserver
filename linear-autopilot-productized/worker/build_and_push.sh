#!/usr/bin/env bash

set -euo pipefail

AWS_PROFILE_DEFAULT=${AWS_PROFILE:-porter-dev-yosef}
AWS_REGION_DEFAULT=${AWS_REGION:-us-east-2}
ECR_REGISTRY_DEFAULT=${ECR_REGISTRY:-992382605253.dkr.ecr.us-east-2.amazonaws.com}
IMAGE_NAME_DEFAULT=${IMAGE_NAME:-linear-autopilot-worker}
PLATFORMS_DEFAULT=${PLATFORMS:-linux/amd64,linux/arm64}
PUSH_DEFAULT=true

usage() {
  cat <<EOF
Usage: $(basename "$0") [--tag TAG] [--profile AWS_PROFILE] [--region AWS_REGION] \\
  [--registry ECR_REGISTRY] [--image IMAGE_NAME] [--platforms PLATFORMS] [--no-push]

Builds and pushes the linear-autopilot-worker image using docker buildx.

Options:
  --tag TAG            Image tag to use. If omitted, uses git short SHA or timestamp.
  --profile PROFILE    AWS profile (default: ${AWS_PROFILE_DEFAULT}).
  --region REGION      AWS region (default: ${AWS_REGION_DEFAULT}).
  --registry REGISTRY  ECR registry (default: ${ECR_REGISTRY_DEFAULT}).
  --image NAME         Image name (default: ${IMAGE_NAME_DEFAULT}).
  --platforms LIST     Target platforms (default: ${PLATFORMS_DEFAULT}).
  --no-push            Build locally without pushing.
  -h, --help           Show this help and exit.
EOF
}

TAG=""
AWS_PROFILE_VAL="${AWS_PROFILE_DEFAULT}"
AWS_REGION_VAL="${AWS_REGION_DEFAULT}"
ECR_REGISTRY_VAL="${ECR_REGISTRY_DEFAULT}"
IMAGE_NAME_VAL="${IMAGE_NAME_DEFAULT}"
PLATFORMS_VAL="${PLATFORMS_DEFAULT}"
PUSH_VAL=${PUSH_DEFAULT}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag)
      TAG="$2"; shift 2 ;;
    --profile)
      AWS_PROFILE_VAL="$2"; shift 2 ;;
    --region)
      AWS_REGION_VAL="$2"; shift 2 ;;
    --registry)
      ECR_REGISTRY_VAL="$2"; shift 2 ;;
    --image)
      IMAGE_NAME_VAL="$2"; shift 2 ;;
    --platforms)
      PLATFORMS_VAL="$2"; shift 2 ;;
    --no-push)
      PUSH_VAL=false; shift 1 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "${TAG}" ]]; then
  if git rev-parse --short HEAD >/dev/null 2>&1; then
    TAG=$(git rev-parse --short HEAD)
  else
    TAG=$(date +%Y%m%d-%H%M%S)
  fi
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FULL_IMAGE_TAG="${ECR_REGISTRY_VAL}/${IMAGE_NAME_VAL}:${TAG}"
FULL_IMAGE_LATEST="${ECR_REGISTRY_VAL}/${IMAGE_NAME_VAL}:latest"

echo "Logging in to ECR: ${ECR_REGISTRY_VAL} (profile=${AWS_PROFILE_VAL}, region=${AWS_REGION_VAL})"
AWS_PROFILE="${AWS_PROFILE_VAL}" aws ecr get-login-password --region "${AWS_REGION_VAL}" | docker login --username AWS --password-stdin "${ECR_REGISTRY_VAL}"

if ! AWS_PROFILE="${AWS_PROFILE_VAL}" aws ecr describe-repositories --repository-names "${IMAGE_NAME_VAL}" --region "${AWS_REGION_VAL}" >/dev/null 2>&1; then
  echo "ECR repository '${IMAGE_NAME_VAL}' not found, creating..."
  AWS_PROFILE="${AWS_PROFILE_VAL}" aws ecr create-repository \
    --repository-name "${IMAGE_NAME_VAL}" \
    --region "${AWS_REGION_VAL}" \
    --image-scanning-configuration scanOnPush=true
fi
BUILD_ARGS=(
  --platform "${PLATFORMS_VAL}"
  -f "${SCRIPT_DIR}/Dockerfile"
  -t "${FULL_IMAGE_TAG}"
  -t "${FULL_IMAGE_LATEST}"
  "${SCRIPT_DIR}"
)

if [[ "${PUSH_VAL}" == true ]]; then
  echo "Building and pushing ${FULL_IMAGE_TAG} (${PLATFORMS_VAL})"
  docker buildx build "${BUILD_ARGS[@]}" --push
else
  echo "Building (no push) ${FULL_IMAGE_TAG} (${PLATFORMS_VAL})"
  docker buildx build "${BUILD_ARGS[@]}" --load
fi

echo "Done. Built image tags:"
echo "  ${FULL_IMAGE_TAG}"
if [[ "${PUSH_VAL}" == true ]]; then
  echo "  ${FULL_IMAGE_LATEST}"
fi
