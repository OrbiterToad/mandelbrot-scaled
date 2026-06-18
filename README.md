# Mandelbrot

A fullscreen Mandelbrot set explorer served via Gunicorn/Flask (NumPy renderer), containerized for local Kubernetes (k3d).

## Prerequisites

- Docker
- [k3d](https://k3d.io) with a running cluster
- `kubectl` configured to talk to that cluster
- Traefik ingress controller enabled on the cluster (default with k3d)

If you don't have a cluster yet:

```bash
k3d cluster create mandelbrot --port "80:80@loadbalancer"
```

## 1. Build the image

```bash
cd mandelbrot
docker build -t mandelbrot:latest .
```

## 2. Import the image into k3d

k3d clusters don't pull from your local Docker daemon by default — you have to import explicitly.

```bash
k3d image import mandelbrot:latest -c <clustername>
```

Replace `<clustername>` with the name of your k3d cluster (`k3d cluster list` to check).

## 3. Deploy to Kubernetes

```bash
kubectl apply -f k8s/
```

This creates:

- `Deployment` — 2 replicas of the Gunicorn/Flask container
- `Service` — ClusterIP on port 80
- `Ingress` — matches all HTTP traffic and forwards to the service (no host filter)

Verify everything is running:

```bash
kubectl get pods,svc,ingress
```

## 4. Open the app

Navigate to [http://localhost](http://localhost) in your browser.

- Scroll to zoom in and out
- Click and drag to pan
- Double-click to zoom in 3× on a point

The current zoom level is shown in the bottom-left corner.

## Teardown

```bash
kubectl delete -f k8s/
```

To also remove the cluster:

```bash
k3d cluster delete <clustername>
```
