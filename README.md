# Mandelbrot

A fullscreen Mandelbrot set explorer served via nginx, containerized for local Kubernetes (k3d).

## Prerequisites

- Docker
- [k3d](https://k3d.io) with a running cluster
- `kubectl` configured to talk to that cluster
- nginx ingress controller enabled on the cluster

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
- `Deployment` — 2 replicas of the nginx container
- `Service` — ClusterIP on port 80
- `Ingress` — routes `mandelbrot.local` to the service

Verify everything is running:

```bash
kubectl get pods,svc,ingress
```

## 4. Add a hosts entry

```bash
echo "127.0.0.1 mandelbrot.local" | sudo tee -a /etc/hosts
```

## 5. Open the app

Navigate to [http://mandelbrot.local](http://mandelbrot.local) in your browser.

Scroll to zoom in and out. The current zoom level is shown in the bottom-left corner.

## Teardown

```bash
kubectl delete -f k8s/
```

To also remove the cluster:

```bash
k3d cluster delete <clustername>
```
