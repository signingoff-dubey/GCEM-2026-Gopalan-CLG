# Builds index.html from animation.template.html and ../opening-animation/rootlens-logo.svg.
#   python build.py
import re
from pathlib import Path

here = Path(__file__).parent
svg = (here.parent / 'opening-animation' / 'rootlens-logo.svg').read_text(encoding='utf8')
block = lambda cls: re.search(rf'<g class="{cls}".*?</g>', svg, re.S).group(0)
word = re.search(r'<path class="word".*?/>', svg, re.S).group(0)


# The orange node's own root, back up to the top of the trunk.
trace = 'M1268.1 1133.65 V928.9 L1162.2 823 L1079.5 739 V440'
hexpts = '1079.5,440 1511,689 1511,1166 1079.5,1415 648,1166 648,689'

html = (here / 'animation.template.html').read_text(encoding='utf8')
for k, v in {'HEX': hexpts, 'ROOTS': block('roots'), 'NODES': block('nodes'), 'WORD': word,
             'HEXLINE': block('hex'), 'TRACE': trace}.items():
    html = html.replace('{{' + k + '}}', v)
assert '{{' not in html
(here / 'index.html').write_text(html, encoding='utf8')
print('index.html', len(html), 'bytes')
