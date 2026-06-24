#!/usr/bin/env bash
set -euo pipefail

# Generate Python gRPC stubs for Yandex SpeechKit v3 AsyncRecognizer.
# Outputs to backend/pipeline/yandexstt_async/ — separate from
# streaming protos in yandexstt/ to avoid package namespace conflicts.

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$REPO_ROOT/backend/pipeline/yandexstt_async"
CLOUDAPI_DIR="/tmp/yandex-cloudapi"

echo "Cloning yandex-cloud/cloudapi..."
rm -rf "$CLOUDAPI_DIR"
git clone --depth 1 https://github.com/yandex-cloud/cloudapi "$CLOUDAPI_DIR"

echo "Generating Python stubs..."
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

uv run python3 -m grpc_tools.protoc \
  -I "$CLOUDAPI_DIR" \
  -I "$CLOUDAPI_DIR/third_party/googleapis" \
  --python_out="$OUT_DIR" \
  --grpc_python_out="$OUT_DIR" \
  yandex/cloud/ai/stt/v3/stt_service.proto \
  yandex/cloud/ai/stt/v3/stt.proto \
  yandex/cloud/operation/operation.proto \
  yandex/cloud/validation.proto \
  yandex/cloud/api/operation.proto \
  google/api/http.proto \
  google/api/annotations.proto

# Create __init__.py for yandex/ directories (regular packages)
find "$OUT_DIR/yandex" -type d -exec touch {}/__init__.py \;

# Do NOT create __init__.py in google/ — it's a namespace package.
# Creating one would shadow the system google.protobuf package.

echo "Done. Generated stubs in $OUT_DIR"
echo "Import with: from backend.pipeline.yandexstt_async.yandex.cloud.ai.stt.v3 import stt_pb2"

rm -rf "$CLOUDAPI_DIR"
