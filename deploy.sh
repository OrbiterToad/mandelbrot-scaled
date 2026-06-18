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

# ── 3. Build Docker image ─────────────────────────────────────────────────────
echo "Building ${IMAGE}..."
docker build -t "${IMAGE}" .

# ── 4. Import image into k3d (bypasses Docker Hub pull) ──────────────────────
echo "Importing image into cluster '${CLUSTER}'..."
k3d image import "${IMAGE}" -c "${CLUSTER}"

# ── 5. Apply manifests ────────────────────────────────────────────────────────
echo "Applying k8s manifests..."
kubectl apply -f k8s/

# ── 6. Force a rollout so pods pick up the newly-imported image ───────────────
# imagePullPolicy: Never means pods won't restart automatically after import.
kubectl rollout restart deployment/mandelbrot
kubectl rollout status deployment/mandelbrot --timeout=120s

echo ""
echo "Ready: http://localhost"
