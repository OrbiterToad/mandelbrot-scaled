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
                      width: int, height: int,
                      yoffset: int = 0, fullheight: int = 0,
                      color: bool = False) -> bytes:
    if fullheight <= 0:
        fullheight = height
    max_iter = _max_iter(zoom)
    scale    = 3.5 / (zoom * width)

    xs = ((np.arange(width, dtype=np.float64) - width * 0.5) * scale + posx)
    # Row (yoffset + i) of the full image maps to strip row i.
    # Full-image row r: y = posy + (fullheight/2 - r) * scale
    local_rows = np.arange(height, dtype=np.float64) + yoffset
    ys = posy + (fullheight * 0.5 - local_rows) * scale

    smooth = _mandelbrot_kernel(xs, ys, max_iter)

    t    = smooth
    v    = 1.0 - np.cos(_PI * t)
    band = 0.18 * np.sin(t * _PI * 6.0)
    br   = np.clip(v + band, 0.0, 1.0)
    if color:
        # Gentle cosine palette: only 3 hue rotations across the full escape range,
        # low amplitude (0.35) so colours stay pastel and never slam to full
        # saturation. Interior points have t==0 / br==0 and stay black.
        cycle = t * 3.0
        r_f = np.clip((0.5 + 0.35 * np.cos(2 * _PI * (cycle + 0.00))) * br, 0.0, 1.0)
        g_f = np.clip((0.5 + 0.35 * np.cos(2 * _PI * (cycle + 0.33))) * br, 0.0, 1.0)
        b_f = np.clip((0.5 + 0.35 * np.cos(2 * _PI * (cycle + 0.67))) * br, 0.0, 1.0)
        rgb = np.stack([
            (r_f * 255).astype(np.uint8),
            (g_f * 255).astype(np.uint8),
            (b_f * 255).astype(np.uint8),
        ], axis=-1)
        img = Image.fromarray(rgb, 'RGB')
    else:
        img = Image.fromarray(np.clip(br * 255, 0, 255).astype(np.uint8), 'L')
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
        yoffset    = int(request.args.get('yoffset',    0))
        fullheight = int(request.args.get('fullheight', 0))
        color      = request.args.get('color', '0') == '1'
        width  = max(1, min(width,  _MAX_DIM))
        height = max(1, min(height, _MAX_DIM))
        if zoom <= 0 or zoom > 1e300:
            raise ValueError
    except (TypeError, ValueError):
        abort(400)

    png = render_mandelbrot(posx, posy, zoom, width, height, yoffset, fullheight, color)
    return png, 200, {
        'Content-Type':  'image/png',
        'Cache-Control': 'no-store',
        'X-Pod-Name':    os.environ.get('POD_NAME', 'unknown'),
    }


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, threaded=True)
