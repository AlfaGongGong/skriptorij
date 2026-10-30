#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""handoff.py — upiši HANDOFF.md i commit-uj."""
import argparse
import datetime
import subprocess
import sys
from pathlib import Path

REPO = Path('/root/skriptorij')
HANDOFF = REPO / 'HANDOFF.md'


def git(*args):
    return subprocess.run(['git'] + list(args), cwd=REPO,
                          capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--zadatak', required=True)
    ap.add_argument('--status', required=True,
                    choices=['dijagnostika', 'staro-novo', 'primena',
                             'test', 'commit', 'prekinuto'])
    ap.add_argument('--sledeci', required=True)
    ap.add_argument('--blokirano', default='nema')
    ap.add_argument('--pitanja', default='nema')
    ap.add_argument('--zavrseno', action='store_true')
    args = ap.parse_args()

    if not (REPO / '.git').exists():
        sys.exit('FAIL: nema .git')
    top = git('rev-parse', '--show-toplevel').stdout.strip()
    if top != str(REPO):
        sys.exit(f'FAIL: repo je {top}')

    head = git('rev-parse', '--short', 'HEAD').stdout.strip()
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

    logs = sorted((REPO / '.logs').glob('*.log'),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    last_log = f'.logs/{logs[0].name}' if logs else '(nema)'

    status_line = f'{args.status} (ZAVRŠENO)' if args.zavrseno else args.status

    content = f"""# HANDOFF — {now}

## Stanje
- Faza: 1
- Zadatak: {args.zadatak}
- Status: {status_line}
- Git HEAD: {head}

## Sledeći korak (tačno)
{args.sledeci}

## Blokirano
{args.blokirano}

## Otvorena pitanja
{args.pitanja}

## Log poslednje sesije
{last_log}
"""
    HANDOFF.write_text(content, encoding='utf-8')
    print(f'Zapisano: {HANDOFF}')

    git('add', 'HANDOFF.md')
    r = git('commit', '-m', f'handoff: {args.zadatak} {status_line}')
    if r.returncode == 0:
        print(f'Commit: {r.stdout.strip().splitlines()[0]}')
    else:
        print('(nema izmena — to je ok)')


if __name__ == '__main__':
    main()
