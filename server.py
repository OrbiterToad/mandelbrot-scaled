import math
import os
from flask import Flask, request, abort, send_file
import numpy as np
from PIL import Image
import io

app = Flask(__name__)

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
_LN2      = np.log(2.0)
_PI       = np.pi
_MAX_DIM  = 1920


def _max_iter(zoom: float) -> int:
    # More iterations at higher zoom so detail doesn't collapse.
    # Caps at 500 to keep CPU time reasonable.
    return min(500, max(100, int(100 * (1 + math.log2(max(1.0, zoom))))))


def render_mandelbrot(posx: float, posy: float, zoom: float,
                      width: int, height: int) -> bytes:
    max_iter = _max_iter(zoom)

    # complex units per pixel
    scale = 3.5 / (zoom * width)

    # Row 0 = top of image = largest imaginary (standard math orientation).
    xs = ((np.arange(width,  dtype=np.float32) - width  * 0.5) * scale + posx)
    ys = (posy + (height * 0.5 - np.arange(height, dtype=np.float32)) * scale)

    C     = (xs[np.newaxis, :] + 1j * ys[:, np.newaxis]).astype(np.complex64)
    Z     = np.zeros_like(C)
    M     = np.full(C.shape, max_iter, dtype=np.float32)
    alive = np.ones(C.shape, dtype=bool)

    for i in range(max_iter):
        Z[alive]  = Z[alive] ** 2 + C[alive]
        z2        = Z.real ** 2 + Z.imag ** 2
        escaped   = alive & (z2 > 4.0)
        M[escaped] = i + 1
        alive[escaped] = False

    in_set = alive
    z2_end = Z.real ** 2 + Z.imag ** 2
    log_zn = np.log(np.where(in_set, 5.0, z2_end)) * 0.5
    nu     = np.log(log_zn / _LN2) / _LN2
    smooth = np.where(in_set, 0.0,
                      np.clip((M + 1.0 - nu) / max_iter, 0.0, 1.0))

    t    = smooth.astype(np.float32)
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
