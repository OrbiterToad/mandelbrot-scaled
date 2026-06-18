import math
import os
import numba
import numpy as np
from flask import Flask, request, abort, send_file
from PIL import Image
import io

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_LN2     = math.log(2.0)
_PI      = math.pi
_MAX_DIM = 1920

# ---------------------------------------------------------------------------
# Numba kernel: escape-time + smooth iteration count, parallelised over rows.
# cache=True writes the compiled binary to __pycache__ so subsequent cold
# starts skip recompilation.
# ---------------------------------------------------------------------------

@numba.njit(parallel=True, fastmath=True, cache=True)
def _mandelbrot_kernel(xs: np.ndarray, ys: np.ndarray, max_iter: int) -> np.ndarray:
    height = ys.shape[0]
    width  = xs.shape[0]
    out    = np.empty((height, width), dtype=np.float32)

    for row in numba.prange(height):   # parallel axis
        cy = float(ys[row])
        for col in range(width):
            cx  = float(xs[col])
            zr  = 0.0
            zi  = 0.0
            zr2 = 0.0
            zi2 = 0.0
            it  = max_iter

            for i in range(max_iter):
                zr2 = zr * zr
                zi2 = zi * zi
                if zr2 + zi2 > 4.0:
                    it = i
                    break
                zi = 2.0 * zr * zi + cy
                zr = zr2 - zi2 + cx

            if it == max_iter:
                out[row, col] = 0.0
            else:
                log_zn = math.log(zr2 + zi2) * 0.5
                nu     = math.log(log_zn / _LN2) / _LN2
                smooth = (it + 1.0 - nu) / max_iter
                out[row, col] = max(0.0, min(1.0, smooth))

    return out


# Compile at import time so the first HTTP request is not penalised.
_mandelbrot_kernel(np.zeros(2, np.float32), np.zeros(2, np.float32), 1)


def _max_iter(zoom: float) -> int:
    return min(500, max(100, int(100 * (1 + math.log2(max(1.0, zoom))))))


def render_mandelbrot(posx: float, posy: float, zoom: float,
                      width: int, height: int) -> bytes:
    max_iter = _max_iter(zoom)
    scale    = 3.5 / (zoom * width)

    xs = ((np.arange(width,  dtype=np.float32) - width  * 0.5) * scale + posx)
    ys = (posy + (height * 0.5 - np.arange(height, dtype=np.float32)) * scale)

    smooth = _mandelbrot_kernel(xs, ys, max_iter)

    t    = smooth
    v    = 1.0 - np.cos(_PI * t)
    band = 0.18 * np.sin(t * _PI * 6.0)
    br   = np.clip(v + band, 0.0, 1.0)
    gray = np.clip(br * 255, 0, 255).astype(np.uint8)

    img = Image.fromarray(gray, 'L')
    buf = io.BytesIO()
    img.save(buf, format='PNG', compress_level=1)
    buf.seek(0)
    return buf.getvalue()


@app.route('/')
def index():
    return send_file(os.path.join(BASE_DIR, 'index.html'))


@app.route('/render')
def render():
    try:
        posx   = float(request.args.get('posx',   -0.5))
        posy   = float(request.args.get('posy',    0.0))
        zoom   = float(request.args.get('zoom',    1.0))
        width  = int(request.args.get('width',   800))
        height = int(request.args.get('height',  600))
        width  = max(1, min(width,  _MAX_DIM))
        height = max(1, min(height, _MAX_DIM))
        if zoom <= 0 or zoom > 1e15:
            raise ValueError
    except (TypeError, ValueError):
        abort(400)

    png = render_mandelbrot(posx, posy, zoom, width, height)
    return png, 200, {
        'Content-Type':  'image/png',
        'Cache-Control': 'no-store',
    }


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, threaded=True)
