"""Conservative README insertion for AfterWard. Run at repository root.
Changes only README.md. Does not overwrite existing judging section.
"""
from pathlib import Path
p = Path('README.md')
text = p.read_text(encoding='utf-8')
marker='## Running AfterWard for judging'
if marker in text:
    raise SystemExit('README already contains a judging section; review manually.')
anchor='## The problem'
if text.count(anchor)!=1:
    raise SystemExit('Expected exactly one `## The problem` anchor; no changes made.')
insert='''## Running AfterWard for judging

**Start here:** [Judge quick-start, reproducible demo scenarios, local/AWS boundaries, MCP evidence and success metrics](docs/judging-guide.md).

The browser is a **Simulated Alexa+** client, not a published Alexa+ add-on. A classic Alexa custom skill was tested in the developer console. All patient data is synthetic. The full experience needs configured AWS resources; the isolated MCP fixture runs only a subset of features without AWS.

**Evidence:** [AWS integrations](docs/aws-integrations.md) · [Product feedback](docs/product-feedback.md) · [15-item friction log](docs/friction-log.md) · [Testing](docs/testing.md) · [Fresh-clone checks](docs/fresh-clone-verification.md) · [Open-source validator](https://github.com/charvimaurya/discharge-letter-check).

'''
text=text.replace(anchor,insert+anchor,1)
p.write_text(text,encoding='utf-8')
print('Updated README.md; review git diff before committing.')
