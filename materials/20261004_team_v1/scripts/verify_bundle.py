"""Verify the exact share allowlist, SHA-256, navigation and public data boundary."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def checked_path(root, rel):
    p=Path(rel)
    if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe manifest path')
    out=root/p
    if not out.resolve().is_relative_to(root.resolve()):raise ValueError('Path escaped package')
    for ancestor in (out, *out.parents):
        if ancestor == root.parent:break
        if ancestor.is_symlink():raise ValueError('Symlink not allowed')
    return out

def verify(root=ROOT):
    root=Path(root)
    manifest=json.loads((root/'MANIFEST.json').read_text())
    records=manifest['files'];wanted={x['path'] for x in records}
    if len(wanted)!=len(records):raise ValueError('Duplicate manifest record')
    actual=set()
    for p in root.rglob('*'):
        rel=p.relative_to(root).as_posix()
        if p.is_symlink():raise ValueError('Symlink in package')
        if rel.startswith('outputs/') or '__pycache__' in p.parts or '.pytest_cache' in p.parts:continue
        if p.is_file() and rel!='MANIFEST.json':actual.add(rel)
    if actual!=wanted:raise ValueError('Package allowlist differs: '+str(sorted(actual^wanted)))
    for record in records:
        p=checked_path(root,record['path'])
        if p.stat().st_size!=record['bytes'] or digest(p)!=record['sha256']:raise ValueError('Hash mismatch: '+record['path'])
        if p.suffix in {'.bin','.safetensors','.joblib','.pem','.key','.sas7bdat','.zip','.log'} or p.name.startswith('.env'):raise ValueError('Private artifact in share')
        if p.suffix in {'.md','.json','.csv','.jsonl','.py','.sas','.toml'}:
            text=p.read_text()
            if re.search(r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY',text):raise ValueError('Credential pattern: '+record['path'])
            if re.search(r'/Users/[A-Za-z0-9_-]+/',text):raise ValueError('Personal machine path: '+record['path'])
            if record['path'].startswith(('data/','presentation/','docs/')) and re.search(r'(?<!\d)01[016789][ .-]?\d{3,4}[ .-]?\d{4}(?!\d)',text):raise ValueError('Phone candidate requires review: '+record['path'])
    for p in root.rglob('*.md'):
        if p.relative_to(root).as_posix().startswith('outputs/'):continue
        for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',p.read_text()):
            if target.startswith(('https://','http://','#','mailto:')):continue
            rel=target.split('#')[0].strip('<>')
            if rel and not (p.parent/rel).exists():raise ValueError('Broken Markdown link: '+str(p.relative_to(root))+' -> '+target)
    print('PASS:',len(records),'files, SHA-256, navigation and public boundary.')
    return len(records)

if __name__=='__main__':verify()
