#!/usr/bin/env bash
set -euo pipefail

CLUSTER="${CLUSTER:-mandelbrot}"
IMAGE="mandelbrot:latest"

# ── 1. Ensure the k3d cluster exists ─────────────────────────────────────────
if ! k3d cluster list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "${CLUSTER}"; then
    echo "Creating k3d cluster '${CLUSTER}'..."
    k3d cluster create "${CLUSTER}" --port "80:80@loadbalancer"
fi

# ── 2. Point kubectl at the cluster ──────────────────────────────────────────
kubectl config use-context "k3d-${CLUSTER}"

# ── 3. Tear down all existing pods before building ────────────────────────────
# Deleting the deployments entirely avoids stuck rolling updates.
kubectl delete deployment mandelbrot mandelbrot-worker mandelbrot-coordinator \
    --ignore-not-found=true
kubectl delete service mandelbrot mandelbrot-worker mandelbrot-coordinator \
    --ignore-not-found=true

# ── 4. Build Docker image ─────────────────────────────────────────────────────
echo "Building ${IMAGE}..."
docker build -t "${IMAGE}" .

# ── 5. Import image into k3d (bypasses Docker Hub pull) ──────────────────────
echo "Importing image into cluster '${CLUSTER}'..."
k3d image import "${IMAGE}" -c "${CLUSTER}"

# ── 6. Apply manifests ────────────────────────────────────────────────────────
echo "Applying k8s manifests..."
kubectl apply -f k8s/

kubectl rollout status deployment/mandelbrot-worker      --timeout=120s
kubectl rollout status deployment/mandelbrot-coordinator --timeout=120s

echo ""
echo "Ready: http://localhost"
