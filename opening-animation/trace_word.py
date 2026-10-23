import sys, numpy as np, potrace
from PIL import Image
im = np.asarray(Image.open(sys.argv[1]).convert('RGB')).astype(int)
r, g, b = im[..., 0], im[..., 1], im[..., 2]
white = (r > 150) & (g > 150) & (b > 150)
white[:1450] = False
ys, xs = np.nonzero(white)
print('bbox', xs.min(), xs.max(), ys.min(), ys.max(), file=sys.stderr)
bm = potrace.Bitmap(~white)
path = bm.trace(turdsize=10, alphamax=0.9, opticurve=True, opttolerance=0.3)
f = lambda p: f'{p.x:.1f} {p.y:.1f}'
out = []
for c in path:
    out.append(f'M{f(c.start_point)}')
    for s in c.segments:
        out.append(f'L{f(s.c)} L{f(s.end_point)}' if s.is_corner else f'C{f(s.c1)} {f(s.c2)} {f(s.end_point)}')
    out.append('Z')
print(''.join(out))
