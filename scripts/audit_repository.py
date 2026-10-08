"""Audit Git-visible files selected by .gitignore; never report secret values."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
RULES={
    'PRIVATE_KEY_MATERIAL':r'-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----',
    'CREDENTIAL_TOKEN_LITERAL':r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})\b',
    'SECRET_ASSIGNMENT_LITERAL':r'(?i)(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|passphrase)\s*[=:]\s*[\"\'][A-Za-z0-9+/=_-]{24,}[\"\']',
    'CREDENTIAL_BEARING_URL':r'https?://[^\s/@:]+:[^\s/@]+@',
    'OLD_MACHINE_REFERENCE':r'(?i)(?:C:[/\\]+Users[/\\]+(?:WJX|WJC)|/mnt/c/Users/(?:WJX|WJC)|C:[/\\]+Project[/\\]+Nebius[/\\]+diagnostics|nebius-wjx|Capture-SessionHost)',
    'REAL_RESOURCE_IDENTIFIER':r'\b(?:tenant|project|devlab|computeinstance)-[a-z0-9]{16,}\b',
}

def candidate_files():
    code,names=git('ls-files','--cached','--others','--exclude-standard')
    if code:raise ValueError('GIT_REPOSITORY_REQUIRED')
    _,deleted=git('diff','--cached','--name-only','--diff-filter=D')
    return sorted(set(names)-set(deleted))

def scan(names):
    risks=[];records=[]
    for name in names:
        p=ROOT/name
        if not p.is_file() or p.is_symlink():risks.append({'file':name,'category':'MISSING_OR_SYMLINK'});continue
        data=p.read_bytes()
        records.append({'file':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        if b'\0' in data:risks.append({'file':name,'category':'BINARY_NOT_ALLOWED'});continue
        try:text=data.decode('utf-8-sig')
        except UnicodeError:risks.append({'file':name,'category':'NON_UTF8_NOT_ALLOWED'});continue
        for category,pattern in RULES.items():
            if category=='OLD_MACHINE_REFERENCE' and (p.suffix not in ('.py','.ps1','.cs') or name=='scripts/audit_repository.py'):
                continue # documentation references and this detector's own rule are not executable dependencies
            if re.search(pattern,text):risks.append({'file':name,'category':category})
        for ip in re.findall(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])',text):
            # RFC 5737 documentation/synthetic ranges; dotted library versions also occur.
            if ip.startswith(('192.0.2.','198.51.100.','203.0.113.')):continue
            if re.search(r'(?i)(?:ip|address|host)\s*[=:]\s*[\"\']'+re.escape(ip),text):
                risks.append({'file':name,'category':'NON_SYNTHETIC_IP_LITERAL'})
        if p.suffix=='.py':
            try:ast.parse(text)
            except SyntaxError:risks.append({'file':name,'category':'PYTHON_SYNTAX'})
        if len(data)>1024**2:risks.append({'file':name,'category':'OVERSIZE_REVIEW_REQUIRED'})
    return records,risks

def git(*args):
    p=subprocess.run(['git','-C',str(ROOT),*args],capture_output=True,text=True)
    return p.returncode,p.stdout.splitlines()

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'.local/audit.json');a=p.parse_args()
    names=candidate_files();records,risks=scan(names)
    ignored=[]
    for name in names:
        code,_=git('check-ignore','--no-index','--quiet','--',name)
        if code==0:ignored.append(name)
    risks.extend({'file':x,'category':'TRACKED_FILE_MATCHES_IGNORE_RULES'} for x in ignored)
    _,staged=git('diff','--cached','--name-only')
    report={'candidate_files':len(names),'total_bytes':sum(x['bytes'] for x in records),
            'largest_bytes':max(x['bytes'] for x in records),'files':records,'risks':risks,
            'staged_files':staged,'binary_candidates':sum(r['category']=='BINARY_NOT_ALLOWED' for r in risks),
            'selection':'.gitignore and Git index; no admission whitelist',
            'scan_limit':'Heuristic candidate-text scan, not a proof that every possible secret is absent; authentication paths and old histories are never read.'}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2))
    print(json.dumps({k:report[k] for k in ('candidate_files','total_bytes','largest_bytes','risks','staged_files','binary_candidates')}))
    return 1 if risks else 0

if __name__=='__main__':raise SystemExit(main())
