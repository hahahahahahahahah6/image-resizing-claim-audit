"""Deterministic documentation and per-module AST auditing."""
import argparse
import ast
import json
from pathlib import Path
import re
import sys
from . import __version__
from .phrases import (IMAGERESIZING, NOIMAGERESIZING, GENERIC_NAMES, PIL_METHODS,
                      PIL_FIT, CV_FUNCTION, SKIMAGE_FUNCTION, RESIZE_CLASSES,
                      RESIZE_SOURCES, RESIZE_REQUIRES_CALL)

def match_phrases(text, phrases):
    text = text.lower()
    found = []
    for phrase in sorted(phrases, key=len, reverse=True):
        start = text.find(phrase)
        while start >= 0:
            found.append(phrase)
            text = text[:start] + ' ' * len(phrase) + text[start + len(phrase):]
            start = text.find(phrase)
    return found, text


def claims(text):
    lines = []
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith('```'):
            fenced = not fenced
        elif not fenced:
            lines.append(line.replace('`', ''))
    denials, remainder = match_phrases('\n'.join(lines), NOIMAGERESIZING)
    positives, _ = match_phrases(remainder, IMAGERESIZING)
    return positives, denials


def evidence(source):
    """Recognize a complete route in a single module, without executing it."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    aliases = {}
    shadowed = {n.name for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split('.')[0]] = alias.name if alias.asname else alias.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                aliases[alias.asname or alias.name] = (node.module or '') + '.' + alias.name

    def resolve(node):
        if isinstance(node, ast.Name):
            if node.id in shadowed:
                return ''
            return aliases.get(node.id, '') if node.id in aliases else node.id
        if isinstance(node, ast.Attribute):
            base = resolve(node.value)
            if not base or node.attr in shadowed:
                return ''
            return base + '.' + node.attr
        return ''

    def imported_or_attribute(node):
        return isinstance(node, ast.Attribute) or (isinstance(node, ast.Name) and node.id in aliases)

    def imported_root(node):
        while isinstance(node, ast.Attribute):
            node = node.value
        return isinstance(node, ast.Name) and node.id in aliases and node.id not in shadowed

    def constructor(node):
        if not isinstance(node, ast.Call):
            return None
        name = resolve(node.func)
        if name == 'PIL.Image.open' and imported_root(node.func):
            return 'picture'
        if imported_root(node.func) and name in {source + '.' + cls for source in RESIZE_SOURCES for cls in RESIZE_CLASSES}:
            return 'transform'
        return None

    instances = {}
    assignments = [n for n in ast.walk(tree) if isinstance(n, (ast.Assign, ast.AnnAssign))]
    for _ in range(len(assignments) + 1):
        changed = False
        for node in assignments:
            kind = constructor(node.value)
            if isinstance(node.value, ast.Name):
                kind = instances.get(node.value.id)
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id not in shadowed and kind and instances.get(target.id) != kind:
                    instances[target.id] = kind
                    changed = True
        if not changed:
            break

    def instance(node):
        if isinstance(node, ast.Name):
            return instances.get(node.id) if node.id not in shadowed else None
        return constructor(node)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = resolve(node.func)
        if name.rsplit('.', 1)[-1] in GENERIC_NAMES and imported_or_attribute(node.func):
            return True
        if name in (PIL_FIT, CV_FUNCTION, SKIMAGE_FUNCTION):
            # Resolved names must originate in an import, not an unbound spelling.
            base = node.func
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name) and base.id in aliases:
                return True
        if RESIZE_REQUIRES_CALL and instance(node.func) == 'transform':
            return True
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in PIL_METHODS and node.func.attr not in shadowed and instance(node.func.value) == 'picture':
                return True
    return False


SKIP_DIRS = {'.git', '__pycache__', 'venv', '.venv', 'env', '.env', 'virtualenv', '.virtualenv'}


def scan(repo, ignore=()):
    repo = Path(repo)
    if not repo.is_dir():
        raise OSError('Repository directory does not exist: ' + str(repo))
    positive = False
    negative = False
    test_positive = False
    has_evidence = False
    decisions = []
    for path in sorted(repo.rglob('*')):
        relative = path.relative_to(repo)
        name = relative.as_posix()
        if any(name.startswith(prefix) for prefix in ignore):
            decisions.append(name + ': ignored prefix')
            continue
        if any(part in SKIP_DIRS for part in relative.parts) or any((repo.joinpath(*relative.parts[:i]) / 'pyvenv.cfg').is_file() for i in range(1, len(relative.parts))):
            continue
        if not path.is_file():
            continue
        is_doc = name == 'README.md' or (relative.parts[0] == 'docs' and path.suffix == '.md')
        is_test = 'tests' in relative.parts[:-1]
        is_source = path.suffix == '.py'
        if not (is_doc or is_test or is_source):
            decisions.append(name + ': outside scan scope')
            continue
        text = path.read_text(encoding='utf-8')
        if is_doc:
            yes, no = claims(text)
            positive |= bool(yes)
            negative |= bool(no)
        elif is_test:
            test_positive |= bool(claims(text)[0])
        matched = is_source and evidence(text)
        has_evidence |= matched
        decisions.append(name + ': ' + ('evidence' if matched else 'scanned; no evidence'))
    findings = []

    def add(rule, severity, message):
        findings.append(dict(rule=rule, severity=severity, verdict='FAIL', message=message))

    if positive and not has_evidence:
        add('documented-image-resizing-claim-false', 'high', 'Documentation asserts the checked feature without a recognized source route.')
    elif test_positive and not positive and not has_evidence:
        add('documented-image-resizing-claim-false', 'medium', 'Only test fixtures assert the checked feature; no recognized source route.')
    if negative and has_evidence:
        add('documented-no-image-resizing-claim-false', 'high', 'Documentation denies the checked feature but a recognized source route exists.')
    return findings, decisions


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def main(argv=None):
    parser = Parser(description='Offline documentation claim auditor')
    parser.add_argument('--version', action='version', version=__version__)
    sub = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    audit = sub.add_parser('audit')
    audit.add_argument('repo', nargs='?', default='.')
    audit.add_argument('--json', action='store_true')
    audit.add_argument('--verbose', action='store_true')
    audit.add_argument('--ignore', action='append', default=[], metavar='PREFIX')
    audit.add_argument('--fail-on', choices=['high', 'medium'], default='high')
    try:
        args = parser.parse_args(argv)
        findings, decisions = scan(Path(args.repo), args.ignore)
        failed = any(f['severity'] == 'high' or args.fail_on == 'medium' for f in findings)
        if args.verbose:
            print('Scope: root README.md, docs/**/*.md, tests/ fixtures, and repository *.py sources', file=sys.stderr)
            for decision in decisions:
                print(decision, file=sys.stderr)
        if args.json:
            print(json.dumps({'verdict': 'FAIL' if failed else 'PASS', 'findings': findings}, indent=2))
        else:
            print('FAIL' if failed else 'PASS')
            for finding in findings:
                print('{severity}: {rule}: {message}'.format(**finding))
        return 2 if failed else 0
    except SystemExit as exc:
        return exc.code
    except (ValueError, OSError, UnicodeError) as exc:
        print('Error: ' + str(exc), file=sys.stderr)
        return 1
