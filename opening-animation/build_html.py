# Inlines rootlens-logo.svg into the opening page and adds the animation-only parts (lens sweep, pulses, tagline).
import sys
svg_path, tpl_path, out = sys.argv[1:4]
svg = open(svg_path, encoding='utf8').read()
hexpts = '1079.5,440 1511,689 1511,1166 1079.5,1415 648,1166 648,689'
extra = f'''<defs>
  <clipPath id="lens"><polygon points="{hexpts}"/></clipPath>
  <linearGradient id="beam" x1="0" x2="1"><stop offset="0" stop-color="#22cede" stop-opacity="0"/><stop offset="0.5" stop-color="#bff6fb" stop-opacity="0.28"/><stop offset="1" stop-color="#22cede" stop-opacity="0"/></linearGradient>
</defs>
<g clip-path="url(#lens)"><rect class="scan" x="989.5" y="430" width="180" height="1000" fill="url(#beam)"/></g>
<circle class="pulse" cx="1268.1" cy="1156.4" r="22.75"/><circle class="pulse" cx="1268.1" cy="1156.4" r="22.75"/>
<text class="tag" x="1079.5" y="1808" text-anchor="middle">ROOT-CAUSE ANALYSIS · DIGITAL MANUFACTURING</text>
</svg>'''
svg = svg.replace('viewBox="360 352 1440 1440"', 'viewBox="360 352 1440 1500"').replace('</svg>', extra)
svg = svg.replace('<g class="nodes"', extra.split('<g clip-path')[0] + '<g class="nodes"', 1).replace(extra.split('<g clip-path')[0] + '<g clip-path', '<g clip-path', 1)
open(out, 'w', encoding='utf8').write(open(tpl_path, encoding='utf8').read().replace('{{SVG}}', svg))
