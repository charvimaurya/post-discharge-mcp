"""Apply small judge-facing documentation edits to two local repositories.
Run: python apply_updates.py --main "C:\\...\\AfterWard-A-Living-Recovery-Plan-for-Alexa" --package "C:\\...\\discharge-letter-check"
Omit --package to change main repository only. Refuses if expected anchors are absent.
"""
import argparse
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--main', required=True, type=Path)
p.add_argument('--package', type=Path)
a=p.parse_args()

def edit(path, transform):
    if not path.is_file():
        print('SKIPPED (missing):',path);return
    orig=path.read_text(encoding='utf-8')
    new=transform(orig)
    if new!=orig:
        path.write_text(new,encoding='utf-8',newline='')
        print('UPDATED:',path)
    else: print('UNCHANGED:',path)

def main_readme(s):
    if '# AfterWard' not in s or '| Demo video | **PENDING_VIDEO_URL** |' not in s:
        raise ValueError('Unexpected README. No edits applied to it.')
    row='| AWS integrations | [docs/aws-integrations.md](docs/aws-integrations.md) |'
    extra='| Judge quick-start | [Running AfterWard for judging](docs/judging-guide.md) |\n| Product feedback | [docs/product-feedback.md](docs/product-feedback.md) |\n| Friction log | [docs/friction-log.md](docs/friction-log.md) |'
    if '| Judge quick-start |' not in s:
        if row not in s: raise ValueError('Missing judge-link insertion anchor')
        s=s.replace(row,row+'\n'+extra,1)
    section='''## Why AfterWard is different

- **Beyond reminders:** A discharge letter becomes a daily plan that can reflect recorded progress, rather than a static list of alarms.
- **Beyond document Q&A:** A patient can report an activity, check what is left, and ask for the supporting words from their own letter.
- **Uncertainty stays visible:** The reusable [discharge-letter-check](https://github.com/charvimaurya/discharge-letter-check) package checks structured extraction fields and flags specified missing or uncertain information for confirmation. It is **not** a clinical verifier and cannot detect every extraction error.

'''
    if '## Why AfterWard is different' not in s:
        needle='## What AfterWard does'
        if needle not in s: raise ValueError('Missing differentiation-section anchor')
        s=s.replace(needle,section+needle,1)
    return s

def guide(s):
    s=s.replace('../README.md#local-setup','../README.md#run-afterward-locally')
    return s

def package_readme(s):
    if '# discharge-letter-check' not in s: raise ValueError('Unexpected package README')
    box='''> **Built for [AfterWard — A Living Recovery Plan for Alexa+](https://github.com/charvimaurya/post-discharge-mcp).** This package provides reusable, structural validation of extracted discharge instructions; it can also be used independently. It does not make clinical safety judgments.

> **Version note:** AfterWard documents integration with the `v0.1.0` release. The [changelog](CHANGELOG.md) describes `0.2.0` changes as **unreleased**; features on `main` may differ from the tagged release.

'''
    if '**Built for [AfterWard' not in s:
        anchor='## What it does'
        if anchor not in s: raise ValueError('Missing package README anchor')
        s=s.replace(anchor,box+anchor,1)
    return s

edit(a.main/'README.md',main_readme)
edit(a.main/'docs'/'REPOSITORY_GUIDE.md',guide)
if a.package: edit(a.package/'README.md',package_readme)
else: print('PACKAGE REPO NOT PROVIDED: no open-source README modification')
print('Video/Devpost placeholders intentionally retained. Review with git diff before commit.')
