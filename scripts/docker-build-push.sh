#!/usr/bin/env bash
# Docker 镜像构建和推送脚本
# 用法: ./scripts/docker-build-push.sh [版本号]
# 示例: ./scripts/docker-build-push.sh v1.0.5

set -euo pipefail

IMAGE_NAME="crachenlie/finvue-web"
VERSION="${1:-latest}"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"

STANDARD_TAGS=(-t "${IMAGE_NAME}:latest")
if [ "${VERSION}" != "latest" ]; then
  STANDARD_TAGS=(-t "${IMAGE_NAME}:${VERSION}" "${STANDARD_TAGS[@]}")
fi

echo "=========================================="
echo "构建并推送 finvue-web Docker 镜像"
echo "版本: $VERSION"
echo "平台: $PLATFORMS"
echo "=========================================="

echo ""
echo "[1/3] 确认 buildx builder..."
docker buildx inspect >/dev/null 2>&1 || docker buildx create --use

echo ""
echo "[2/3] 构建并推送标准镜像 (Dockerfile)..."
docker buildx build \
  --platform "${PLATFORMS}" \
  "${STANDARD_TAGS[@]}" \
  --push .

echo ""
echo "[3/3] 构建并推送 all-in-one 镜像 (Dockerfile.allinone)..."
docker buildx build \
  --platform "${PLATFORMS}" \
  -f Dockerfile.allinone \
  -t "${IMAGE_NAME}:allinone" \
  --push .

echo ""
echo "完成!"
echo "=========================================="
echo "已推送以下镜像:"
if [ "${VERSION}" != "latest" ]; then
  echo "  - ${IMAGE_NAME}:${VERSION}"
fi
echo "  - ${IMAGE_NAME}:latest"
echo "  - ${IMAGE_NAME}:allinone"
echo "=========================================="
