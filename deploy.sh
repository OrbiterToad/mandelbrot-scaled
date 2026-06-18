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

# ── 5. Remove old single-pod deployment if upgrading from previous layout ─────
kubectl delete deployment mandelbrot --ignore-not-found=true
kubectl delete service mandelbrot    --ignore-not-found=true

# ── 6. Kill all replicas immediately so apply brings up fresh pods at once ────
# Rolling updates wait for each pod's readiness probe before proceeding.
# Scaling to 0 first avoids that — all new pods start in parallel.
for deploy in mandelbrot-worker mandelbrot-coordinator; do
    kubectl get deployment "$deploy" &>/dev/null && \
        kubectl scale deployment/"$deploy" --replicas=0 || true
done

# ── 7. Apply manifests — restores desired replica counts with the new image ───
echo "Applying k8s manifests..."
kubectl apply -f k8s/

kubectl rollout status deployment/mandelbrot-worker      --timeout=120s
kubectl rollout status deployment/mandelbrot-coordinator --timeout=120s

echo ""
echo "Ready: http://localhost"
