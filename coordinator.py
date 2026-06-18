import io
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests as http
from flask import Flask, request, abort, send_file, jsonify
from PIL import Image

app = Flask(__name__)

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
WORKER_URL  = os.environ.get('WORKER_URL', 'http://mandelbrot-worker')
NUM_STRIPS  = 3
_MAX_DIM    = 1920

_K8S_API    = 'https://kubernetes.default.svc'
_TOKEN_FILE = '/var/run/secrets/kubernetes.io/serviceaccount/token'
_CA_FILE    = '/var/run/secrets/kubernetes.io/serviceaccount/ca.crt'


def _fetch_strip(posx, posy, zoom, width, yoffset, strip_height, fullheight):
    url = (
        f"{WORKER_URL}/render"
        f"?posx={posx}&posy={posy}&zoom={zoom}"
        f"&width={width}&height={strip_height}"
        f"&yoffset={yoffset}&fullheight={fullheight}"
    )
    resp = http.get(url, timeout=120)
    resp.raise_for_status()
    return yoffset, Image.open(io.BytesIO(resp.content))


def _fetch_pod_active(pod_ip):
    try:
        r = http.get(f'http://{pod_ip}/status', timeout=2)
        r.raise_for_status()
        return r.json().get('active', 0)
    except Exception:
        return None


@app.route('/status')
def status():
    try:
        token = open(_TOKEN_FILE).read().strip()
        resp  = http.get(
            f'{_K8S_API}/api/v1/namespaces/default/pods',
            params={'labelSelector': 'app=mandelbrot-worker'},
            headers={'Authorization': f'Bearer {token}'},
            verify=_CA_FILE,
            timeout=5,
        )
        resp.raise_for_status()

        # Build pod list from k8s metadata.
        pods = []
        for item in resp.json().get('items', []):
            name       = item['metadata']['name']
            phase      = item['status'].get('phase', 'Unknown')
            pod_ip     = item['status'].get('podIP')
            conditions = item['status'].get('conditions', [])
            ready      = any(
                c['type'] == 'Ready' and c['status'] == 'True'
                for c in conditions
            )
            pods.append({'name': name, 'phase': phase, 'ready': ready,
                         'pod_ip': pod_ip, 'active': None})

        # Call each running pod's /status directly (bypasses the Service load
        # balancer) to get its live active-render count.
        running = [p for p in pods if p['pod_ip'] and p['phase'] == 'Running']
        with ThreadPoolExecutor(max_workers=len(running) or 1) as pool:
            futures = {pool.submit(_fetch_pod_active, p['pod_ip']): p for p in running}
            for future in as_completed(futures):
                futures[future]['active'] = future.result()

        # Drop internal pod_ip before sending to browser.
        for p in pods:
            p.pop('pod_ip', None)

        return jsonify(pods=pods)
    except Exception as e:
        return jsonify(pods=[], error=str(e))


@app.route('/')
def index():
    return send_file(os.path.join(BASE_DIR, 'index.html'))


@app.route('/render')
def render():
    try:
        posx       = float(request.args.get('posx',   -0.5))
        posy       = float(request.args.get('posy',    0.0))
        zoom       = float(request.args.get('zoom',    1.0))
        width      = int(request.args.get('width',   800))
        fullheight = int(request.args.get('height',  600))
        width      = max(1, min(width,      _MAX_DIM))
        fullheight = max(1, min(fullheight, _MAX_DIM))
        if zoom <= 0 or zoom > 1e300:
            raise ValueError
    except (TypeError, ValueError):
        abort(400)

    # Divide the image into NUM_STRIPS horizontal strips.
    # The last strip absorbs any remainder from integer division.
    strip_h = fullheight // NUM_STRIPS
    strips  = []
    for i in range(NUM_STRIPS):
        yoff = i * strip_h
        h    = strip_h if i < NUM_STRIPS - 1 else fullheight - yoff
        strips.append((yoff, h))

    # Fire all strip requests to workers in parallel.
    result = Image.new('L', (width, fullheight))
    try:
        with ThreadPoolExecutor(max_workers=NUM_STRIPS) as pool:
            futures = {
                pool.submit(
                    _fetch_strip, posx, posy, zoom, width, yoff, h, fullheight
                ): yoff
                for yoff, h in strips
            }
            for future in as_completed(futures):
                yoffset, strip_img = future.result()
                result.paste(strip_img, (0, yoffset))
    except Exception:
        abort(502)

    buf = io.BytesIO()
    result.save(buf, format='PNG', compress_level=1)
    buf.seek(0)
    return buf.getvalue(), 200, {
        'Content-Type':  'image/png',
        'Cache-Control': 'no-store',
    }


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, threaded=True)
