# Builds rootlens-logo.svg from hand-measured geometry (2160px source space) plus the potrace'd wordmark.
import sys
word_d, out = open(sys.argv[1]).read().strip(), sys.argv[2]
CY, OR = '#22cede', '#fe6a0c'
M = lambda x: round(2159 - x, 1)  # mirror across the trunk (x = 1079.5)
R = 22.75  # node ring radius (centre of the stroke)

# (path points from the trunk side outwards, node centre or None, depth for the draw order)
left = [
    ([(1079.5, 739), (996.8, 823), (905, 823), (870, 788), (783.5 + R, 788)], (783.5, 788.1), 1),
    ([(905, 823), (824, 904.5), (757.4 + R, 904.5)], (757.4, 904.5), 2),
    ([(996.8, 823), (996.8, 958.3 - R)], (996.8, 958.3), 2),
    ([(996.8, 823), (787.8, 1032), (787.8, 1096.7 - R)], (787.8, 1096.7), 2),
    ([(891.2, 928.6), (891.2, 1156.1 - R)], (891.2, 1156.1), 3),
]
paths, nodes = [], []
for pts, node, depth in left:
    for side in (0, 1):
        p = [(M(x) if side else x, y) for x, y in pts]
        n = (M(node[0]) if side else node[0], node[1])
        if side and node[0] == 996.8: n = (1162.6, 979.3); p[-1] = (p[-1][0], 979.3 - R)
        if side and node[0] == 891.2: n = (1268.1, 1156.4)
        paths.append((p, depth)); nodes.append((n, depth, OR if side and node[0] == 891.2 else CY))
# centre roots
paths += [([(1079.5, 986), (984.2, 1081), (984.2, 1212.4 - R)], 2), ([(984.2, 1081), (1079.6, 1176.6), (1079.6, 1271 - R)], 3),
          ([(1098, 1039), (1175, 1116), (1175, 1212.3 - R)], 3)]
nodes += [((984.2, 1212.4), 2, CY), ((1079.6, 1271), 3, CY), ((1175, 1212.3), 3, CY)]

poly = lambda p: 'M' + ' L'.join(f'{x} {y}' for x, y in p)
hexl = [(1079.5, 440), (648, 689), (648, 1166), (1079.5, 1415)]
hexr = [(1079.5, 440), (1511, 689), (1511, 1166), (1079.5, 1415)]

el = []
el.append(f'<g class="hex" fill="none" stroke="{CY}" stroke-width="21" stroke-linejoin="miter">')
el += [f'  <path class="draw" style="--d:0" pathLength="1" d="{poly(h)}"/>' for h in (hexl, hexr)]
el.append('</g>')
el.append(f'<g class="roots" fill="none" stroke="{CY}" stroke-width="21" stroke-linejoin="miter">')
el.append(f'  <path class="draw trunk" style="--d:1" pathLength="1" d="M1079.5 429 V986"/>')
el += [f'  <path class="draw" style="--d:{2 + depth * 0.5}" pathLength="1" d="{poly(p)}"/>' for p, depth in paths]
el.append('</g>')
el.append('<g class="nodes" fill="none" stroke-width="20.5">')
for (x, y), depth, col in nodes:
    cls = 'node root' if col == OR else 'node'
    el.append(f'  <circle class="{cls}" style="--d:{2.5 + depth * 0.5}" cx="{x}" cy="{y}" r="{R}" stroke="{col}"/>')
el.append('</g>')
el.append(f'<path class="word" fill="#ffffff" d="{word_d}"/>')

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="360 352 1440 1440" role="img" aria-label="RootLens">
<rect class="bg" x="360" y="352" width="1440" height="1440" fill="#171c20"/>
{chr(10).join(el)}
</svg>
'''
open(out, 'w', encoding='utf8').write(svg)
