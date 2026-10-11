#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")"
[ -f .env ] || { echo "ERROR: .env not found"; exit 1; }
cp -a .env ".env.backup-1.5.0-$(date +%Y%m%d-%H%M%S)"
# Migrate only Kira's old stock image defaults; preserve custom user endpoints/models.
sed -i 's#http://local-image:7860#http://comfyui:8188#g' .env || true
if grep -q '^LOCAL_IMAGE_MODEL_FILE=v1-5-pruned_Q4_0.gguf$' .env; then sed -i 's/^LOCAL_IMAGE_MODEL_FILE=.*/COMFYUI_CHECKPOINT=DreamShaper_8_pruned.safetensors/' .env; fi
if grep -q '^LOCAL_IMAGE_MODEL_URL=.*kostakoff/stable-diffusion-v1-5-GGUF' .env; then sed -i '/^LOCAL_IMAGE_MODEL_URL=/d' .env; fi
grep -q '^COMFYUI_VERSION=' .env || echo 'COMFYUI_VERSION=v0.36.0' >> .env
grep -q '^COMFYUI_CHECKPOINT=' .env || echo 'COMFYUI_CHECKPOINT=DreamShaper_8_pruned.safetensors' >> .env
docker compose config -q
docker compose --profile image pull redis ollama comfyui-model || true
docker compose --profile image up -d --build --remove-orphans redis comfyui kira
printf '\nKira 1.5 started. Check: docker compose ps && docker compose logs --tail=100 comfyui kira\n'
