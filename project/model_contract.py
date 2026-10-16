"""Small closed data contract shared by CPU transport and GPU executor."""
import hashlib
import hmac
import io
import json
import math
from pathlib import Path
import re
import tarfile
import time
import copy
import gzip
from pathlib import PurePosixPath

from inference.jobs import RUN_CONFIG,ID
from lighting import canonical
from security import runtime_file

ROOT=Path(__file__).resolve().parent.parent
MAX=32*1024*1024


def grant_file(path,session,resource,clock=time.time):
    g=json.loads(runtime_file(path,ROOT).decode('utf-8'))
    required={'schemaVersion','sessionId','resourceId','hostIdentity','hostConfirmed','modelLicenseAck',
              'expiresAt','budgetUsdIncludingTax','approvalReference','maxJobs','allowedOriginalSha256',
              'allowedRecipeKeys','allowedMetadata'}
    dynamic=isinstance(g,dict) and g.get('schemaVersion')==2
    if dynamic:required=(required-{'allowedOriginalSha256','allowedRecipeKeys','allowedMetadata'})|{'jobAuthorization'}
    if (not isinstance(g,dict) or set(g)!=required or type(g['schemaVersion']) is not int or g['schemaVersion'] not in (1,2) or
            g['sessionId']!=session or g['resourceId']!=resource or g['hostConfirmed'] is not True or
            g['modelLicenseAck'] is not True or not isinstance(g['hostIdentity'],dict) or not g['hostIdentity'] or
            type(g['expiresAt']) not in (float,int) or not math.isfinite(g['expiresAt']) or g['expiresAt']<=clock() or
            type(g['budgetUsdIncludingTax']) not in (int,float) or not math.isfinite(g['budgetUsdIncludingTax']) or g['budgetUsdIncludingTax']<=0 or
            not isinstance(g['approvalReference'],str) or not 1<=len(g['approvalReference'])<=200 or
            type(g['maxJobs']) is not int or not 1<=g['maxJobs']<=20):
        raise ValueError('NEW_MODEL_GRANT_REQUIRED')
    if dynamic:
        auth=g['jobAuthorization']
        if (not isinstance(auth,dict) or set(auth)!={'algorithm','keyHex','owner'} or auth['algorithm']!='hmac-sha256-v1' or
                not isinstance(auth['keyHex'],str) or not re.fullmatch('[a-f0-9]{64}',auth['keyHex']) or
                not isinstance(auth['owner'],str) or not 1<=len(auth['owner'])<=200):
            raise ValueError('PRIVATE_JOB_SIGNING_BINDING_REQUIRED')
        return g
    for name in ('allowedOriginalSha256','allowedRecipeKeys'):
        if not isinstance(g[name],list) or not 1<=len(g[name])<=20 or any(not isinstance(x,str) or not re.fullmatch('[a-f0-9]{64}',x) for x in g[name]):
            raise ValueError('EXACT_MODEL_INPUT_AND_RECIPE_APPROVAL_REQUIRED')
    if (not isinstance(g['allowedMetadata'],list) or not 1<=len(g['allowedMetadata'])<=20 or
            any(not isinstance(x,dict) or set(x)!={'owner','fingerprint'} or not isinstance(x['owner'],str) or
                not isinstance(x['fingerprint'],str) or not re.fullmatch('[a-f0-9]{64}',x['fingerprint']) for x in g['allowedMetadata'])):
        raise ValueError('EXACT_MODEL_OWNER_APPROVAL_REQUIRED')
    return g


def check_request(request,grant):
    if (not isinstance(request,dict) or any(not isinstance(request.get(k),str) or not ID.fullmatch(request[k]) for k in ('taskId','nonce')) or
            any(request.get('runConfig',{}).get(k)!=v for k,v in RUN_CONFIG.items()) or
            request['runConfig'].get('weightVerification')!='full' or
            request['runConfig'].get('weightContentHashesChecked') is not True or
            (grant.get('schemaVersion')!=2 and (request['original']['sha256'] not in grant['allowedOriginalSha256'] or
            request['preset'].get('recipeKey') not in grant['allowedRecipeKeys'])) or
            len(request.get('presets',[]))!=1 or request['presets'][0]!=request['preset'] or
            request['runConfig'].get('lightingAdapterVersion')!='single-scheme-hdr-adapter-v1'):
        raise ValueError('MODEL_REQUEST_OUTSIDE_APPROVED_SCOPE')
    if hashlib.sha256(canonical(request['preset'].get('parameters')).encode()).hexdigest()!=request['preset']['recipeKey']:
        raise ValueError('MODEL_RECIPE_PARAMETERS_HASH_MISMATCH')
    if request.get('requiredInverseReuse') is not None:
        raise ValueError('HTTPS_REQUIRED_INVERSE_REUSE_ARTIFACT_NOT_PROVIDED')


def model_request(request):
    value=copy.deepcopy(request)
    value['input']={k:v for k,v in value['input'].items() if k not in ('name','url','originalUrl')}
    return value


def request_sha(request):return hashlib.sha256(canonical(model_request(request)).encode()).hexdigest()


def pack_input(folder,request,authorization=None):
    folder=Path(folder);data={'request.json':canonical(model_request(request)).encode(),'inputs/photo.png':(folder/'inputs/photo.png').read_bytes()}
    if hashlib.sha256(data['inputs/photo.png']).hexdigest()!=request['input']['sha256']:raise ValueError('INPUT_CHANGED')
    derived=request['preset'].get('derivedHdrSha256')
    if derived:
        path=folder/'inputs/lighting.hdr'
        if path.is_symlink():raise ValueError('HDR_PATH_UNSAFE')
        data['inputs/lighting.hdr']=path.read_bytes()
        if hashlib.sha256(data['inputs/lighting.hdr']).hexdigest()!=derived:raise ValueError('HDR_CHANGED')
    if authorization is not None:data['authorization.json']=canonical(authorization).encode()
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
        for name,raw in data.items():
            if len(raw)>MAX:raise ValueError('ARTIFACT_TOO_LARGE')
            member=tarfile.TarInfo(name);member.size=len(raw);member.mode=0o600;member.mtime=0
            archive.addfile(member,io.BytesIO(raw))
    value=buffer.getvalue()
    if len(value)>MAX:raise ValueError('ARTIFACT_TOO_LARGE')
    return value


def unpack_input(payload):
    if len(payload)>MAX:raise ValueError('ARTIFACT_TOO_LARGE')
    files={};total=0
    with bounded_tar(payload) as archive:
        for member in archive:
            total+=member.size
            if (not member.isfile() or member.size<0 or member.name not in ('request.json','inputs/photo.png','inputs/lighting.hdr','authorization.json') or
                    member.name in files or member.size>MAX or total>2*MAX):raise ValueError('UNSAFE_INPUT_ARCHIVE')
            files[member.name]=archive.extractfile(member).read()
    if not {'request.json','inputs/photo.png'}<=set(files):raise ValueError('INPUT_FILES_REQUIRED')
    request=json.loads(files['request.json'])
    if hashlib.sha256(files['inputs/photo.png']).hexdigest()!=request['input']['sha256']:raise ValueError('INPUT_CHANGED')
    derived=request['preset'].get('derivedHdrSha256')
    if bool(derived)!=('inputs/lighting.hdr' in files) or (derived and hashlib.sha256(files['inputs/lighting.hdr']).hexdigest()!=derived):
        raise ValueError('HDR_CHANGED')
    return request,files


def bounded_tar(payload):
    if len(payload)>MAX:raise ValueError('ARTIFACT_TOO_LARGE')
    # Bound expansion BEFORE tarfile parses PAX/long-name pseudo-members.
    limit=2*MAX+2*1024*1024
    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as compressed:raw=compressed.read(limit+1)
    if len(raw)>limit:raise ValueError('ARTIFACT_EXPANSION_TOO_LARGE')
    return tarfile.open(fileobj=io.BytesIO(raw),mode='r:')


def validate_result_archive(payload):
    names=set();total=0
    with bounded_tar(payload) as archive:
        for member in archive:
            total+=member.size;path=PurePosixPath(member.name)
            if (not member.isfile() or not 0<=member.size<=MAX or total>2*MAX or len(names)>=1024 or
                    member.name in names or path.is_absolute() or '..' in path.parts or ':' in member.name or '\\' in member.name):
                raise ValueError('UNSAFE_RESULT_ARCHIVE')
            names.add(member.name)


def job_authorization(request,grant):
    """Private CPU signs exact canonical request, bound to one warm session.

    Transport keeps this outside request.json, avoiding circular request hashes.
    No key material is included in the uploaded authorization.
    """
    if grant.get('schemaVersion')!=2:raise ValueError('DYNAMIC_JOB_GRANT_REQUIRED')
    check_request(request,grant)
    body={'schemaVersion':1,'sessionId':grant['sessionId'],'resourceId':grant['resourceId'],
          'hostIdentity':grant['hostIdentity'],'owner':grant['jobAuthorization']['owner'],
          'taskId':request['taskId'],'nonce':request['nonce'],'requestSha256':request_sha(request),
          'expiresAt':grant['expiresAt'],'approvalReference':grant['approvalReference']}
    signature=hmac.new(bytes.fromhex(grant['jobAuthorization']['keyHex']),canonical(body).encode(),hashlib.sha256).hexdigest()
    return {'body':body,'signature':signature}


def verify_job_authorization(request,grant,authorization,clock=time.time):
    if (not isinstance(authorization,dict) or set(authorization)!={'body','signature'} or
            not isinstance(authorization['signature'],str) or not re.fullmatch('[a-f0-9]{64}',authorization['signature'])):
        raise ValueError('SIGNED_JOB_AUTHORIZATION_REQUIRED')
    if clock()>=grant['expiresAt']:raise ValueError('JOB_AUTHORIZATION_EXPIRED')
    expected=job_authorization(request,grant)
    if authorization['body']!=expected['body'] or not hmac.compare_digest(authorization['signature'],expected['signature']):
        raise ValueError('JOB_AUTHORIZATION_BINDING_MISMATCH')
    return True
