#!/usr/bin/env python3
"""Skill package lint — 每次发布前必须通过."""
import yaml, sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
errors = []
skill_text = (SKILL / 'SKILL.md').read_text(encoding='utf-8')

for f in (SKILL / 'schemas').glob('*.yaml'):
    try:
        yaml.safe_load(f.read_text(encoding='utf-8'))
    except Exception as e:
        errors.append(f"Schema {f.name}: {e}")

tpl = SKILL / 'templates' / 'main-domain-design-template.yaml'
try:
    tdata = yaml.safe_load(tpl.read_text(encoding='utf-8'))
except Exception as e:
    errors.append(f"Template: {e}")

try:
    schema = yaml.safe_load((SKILL / 'schemas' / 'main-domain-functional-design.schema.yaml').read_text(encoding='utf-8'))
    req = schema.get('main_domain_functional_design', {}).get('required', [])
    tkeys = list(tdata.get('main_domain_functional_design', {}).keys())
    for r in req:
        if r not in tkeys:
            errors.append(f"Template missing schema required: {r}")
except Exception as e:
    errors.append(f"Schema-template check: {e}")

if (SKILL / 'workspace').exists():
    errors.append("Skill package contains workspace/")

for script_name in sorted(set(__import__('re').findall(r"scripts/([A-Za-z0-9_\-]+\.py)", skill_text))):
    if not (SKILL / 'scripts' / script_name).exists():
        errors.append(f"SKILL.md references missing script: scripts/{script_name}")

policy = (SKILL / 'references' / 'supporting-domain-policy.md').read_text(encoding='utf-8')
for banned in ['not_required', 'reference_only', 'platform_capability', 'recommended_p2: false']:
    if banned in policy.replace('禁止使用：', ''):
        errors.append(f"supporting-domain-policy contains banned legacy token: {banned}")

try:
    pages = tdata['main_domain_functional_design']['modules'][0]['page_design']['pages'][0]
    for key in ['style_summary', 'data_sections', 'interactions', 'permissions']:
        if key not in pages:
            errors.append(f"Template page example missing {key}")
    issue = tdata['main_domain_functional_design']['modules'][0]['open_issues'][0]
    for key in ['blocking', 'source']:
        if key not in issue:
            errors.append(f"Template open_issues example missing {key}")
except Exception as e:
    errors.append(f"Template deep structure check: {e}")

review_template = (SKILL / 'templates' / 'review-checklist.template.md').read_text(encoding='utf-8')
for marker in ['review_meta', 'Review 结论', '输入确认', '模块逐项检查', 'Source ID', '泛化设计', '问题清单', 'Re-report']:
    if marker not in review_template:
        errors.append(f"Review template missing marker: {marker}")

for script in (SKILL / 'scripts').glob('*.py'):
    text = script.read_text(encoding='utf-8')
    if script.name != 'lint_skill_package.py' and 'sys.argv[2]' in text:
        errors.append(f"{script.name}: uses sys.argv[2]; use argparse")

if errors:
    print(f"FAIL: {len(errors)} errors")
    for e in errors: print(f"  - {e}")
    sys.exit(1)
print("PASS: Skill package lint passed")
