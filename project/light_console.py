"""Bounded lighting recipes and deterministic linear-RGB distant illumination.

No model calls. Radiance RGBE is the portable interchange; raw imports are kept.
Angles are environment-map coordinates, not calibrated photograph coordinates.
"""
import copy
import hashlib
import io
import json
import math
import re
from pathlib import Path

VERSION = 'sphere-gaussian-rgbe-v1'
PREPROCESS = 'flip180-pixel-roll-log10000-v1'
COLOR = 'linear-srgb-rgbe;picker-srgb-decoded-v1'
MAX_BYTES = 32 * 1024 * 1024

def sha(data): return hashlib.sha256(data).hexdigest()
def exact(v, fields):
    if not isinstance(v, dict) or set(v) != set(fields): raise ValueError('UNKNOWN_OR_MISSING_FIELDS')
def number(v, lo, hi):
    if type(v) not in (int, float) or not math.isfinite(v) or not lo <= v <= hi: raise ValueError('FINITE_BOUNDED_NUMBER_REQUIRED')
    return 0 if v == 0 else v
def angle(v): return number(v, -1e6, 1e6) % 360
def color(v):
    if type(v) is not str or not re.fullmatch('#[0-9a-fA-F]{6}', v): raise ValueError('SRGB_HEX_REQUIRED')
    return v.lower()
def text(v):
    if type(v) is not str or not 1 <= len(v.strip()) <= 40 or any(ord(c)<32 for c in v): raise ValueError('BOUNDED_NAME_REQUIRED')
    return v.strip()

def normalize(v, environments):
    exact(v, ('schemaVersion','mode','environmentId','environmentSha256','offsetDeg','strength','ambient','zones','synthesizerVersion','preprocessingVersion','colorConvention'))
    if type(v['schemaVersion']) is not int or v['schemaVersion'] != 2 or v['mode'] not in ('environment','procedural'): raise ValueError('LIGHTING_SCHEMA_REQUIRED')
    if v['synthesizerVersion'] != VERSION or v['preprocessingVersion'] != PREPROCESS or v['colorConvention'] != COLOR: raise ValueError('PROCESSING_VERSION_MISMATCH')
    out=copy.deepcopy(v);out['offsetDeg']=angle(v['offsetDeg']);out['strength']=number(v['strength'], .25, 4)
    exact(v['ambient'], ('strength','color'));out['ambient']={'strength':number(v['ambient']['strength'],0,4),'color':color(v['ambient']['color'])}
    if type(v['zones']) is not list or len(v['zones'])>3: raise ValueError('MAX_THREE_ZONES')
    zones=[]
    for z in v['zones']:
        exact(z,('id','name','enabled','azimuthDeg','elevationDeg','strength','color','sizeDeg'))
        if type(z['id']) is not str or not re.fullmatch('[a-zA-Z0-9_-]{1,32}',z['id']) or type(z['enabled']) is not bool: raise ValueError('ZONE_ID_OR_SWITCH_INVALID')
        zones.append({**z,'name':text(z['name']),'azimuthDeg':angle(z['azimuthDeg']),'elevationDeg':number(z['elevationDeg'],-90,90),'strength':number(z['strength'],0,16),'color':color(z['color']),'sizeDeg':number(z['sizeDeg'],2,120)})
    if len({z['id'] for z in zones}) != len(zones): raise ValueError('DUPLICATE_ZONE_ID')
    out['zones']=zones
    if v['mode']=='environment':
        e=environments.get(v['environmentId'])
        if not e or v['environmentSha256']!=e['sha256']: raise ValueError('ENVIRONMENT_CONTENT_MISMATCH')
    elif v['environmentId'] is not None or v['environmentSha256'] is not None: raise ValueError('PROCEDURAL_HAS_NO_SOURCE_ENVIRONMENT')
    return out

def initial(environment):
    return {'schemaVersion':2,'mode':'environment','environmentId':environment['id'],'environmentSha256':environment['sha256'],'offsetDeg':0,'strength':1,'ambient':{'strength':.03,'color':'#ffffff'},'zones':[], 'synthesizerVersion':VERSION,'preprocessingVersion':PREPROCESS,'colorConvention':COLOR}

def srgb(hexcolor):
    import numpy as np
    v=np.array([int(hexcolor[i:i+2],16)/255 for i in (1,3,5)],dtype=np.float64)
    return np.where(v<=.04045,v/12.92,((v+.055)/1.055)**2.4)

def synthesize(recipe, width=512, height=256):
    import numpy as np
    if type(width) is not int or type(height) is not int or width!=2*height or not 32<=height<=1024: raise ValueError('BOUNDED_LATLONG_SIZE_REQUIRED')
    lon=(np.arange(width)+.5)*2*np.pi/width
    lat=np.pi/2-(np.arange(height)+.5)*np.pi/height
    x=np.cos(lat)[:,None]*np.sin(lon)[None,:];y=np.sin(lat)[:,None]*np.ones((1,width));z=np.cos(lat)[:,None]*np.cos(lon)[None,:]
    image=np.broadcast_to(srgb(recipe['ambient']['color'])*recipe['ambient']['strength'],(height,width,3)).copy()
    for light in recipe['zones']:
        if not light['enabled']: continue
        a,e=np.deg2rad([light['azimuthDeg'],light['elevationDeg']])
        dot=np.clip(x*np.cos(e)*np.sin(a)+y*np.sin(e)+z*np.cos(e)*np.cos(a),-1,1)
        # Great-circle Gaussian, full width at half maximum in angular degrees.
        sigma=np.deg2rad(light['sizeDeg'])/(2*np.sqrt(2*np.log(2)))
        weight=np.exp(-.5*(np.arccos(dot)/sigma)**2)
        image+=weight[:,:,None]*srgb(light['color'])*light['strength']
    if not np.isfinite(image).all() or image.max()>65504: raise ValueError('HDR_RANGE_INVALID')
    return image.astype('<f4')

def encode_hdr(image):
    import numpy as np
    h,w,c=image.shape
    m=image.max(axis=2);mantissa,exponent=np.frexp(m)
    scale=np.divide(mantissa*256,m,out=np.zeros_like(m),where=m>1e-32)
    rgb=np.clip(image*scale[:,:,None],0,255).astype('uint8');exp=np.where(m>1e-32,exponent+128,0).astype('uint8')
    raw=np.concatenate((rgb,exp[:,:,None]),axis=2)
    parts=[f'#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y {h} +X {w}\n'.encode()]
    for row in raw:
        parts.append(bytes((2,2,w>>8,w&255)))
        for ch in range(4):
            for start in range(0,w,128):
                literal=row[start:start+128,ch].tobytes();parts.append(bytes((len(literal),))+literal)
    return b''.join(parts)

def decode_hdr(data, max_value=65504):
    import numpy as np
    if not 0<len(data)<=MAX_BYTES: raise ValueError('HDR_FILE_TOO_LARGE')
    stream=io.BytesIO(data)
    if stream.readline().strip() not in (b'#?RADIANCE',b'#?RGBE'): raise ValueError('RADIANCE_HDR_REQUIRED')
    header=[]
    for _ in range(64):
        line=stream.readline(1024)
        if len(line)>=1024: raise ValueError('HDR_HEADER_TOO_LARGE')
        if not line.strip():break
        header.append(line.strip())
    else: raise ValueError('HDR_HEADER_INVALID')
    if b'FORMAT=32-bit_rle_rgbe' not in header: raise ValueError('RGBE_FORMAT_REQUIRED')
    dims=re.fullmatch(rb'-Y (\d+) \+X (\d+)\s*',stream.readline(100))
    if not dims: raise ValueError('HDR_ORIENTATION_UNSUPPORTED')
    h,w=map(int,dims.groups())
    if not 16<=h<=2048 or not 32<=w<=4096 or w!=2*h or h*w>8388608: raise ValueError('HDR_DIMENSIONS_INVALID')
    raw=np.empty((h,w,4),dtype='uint8')
    for row in range(h):
        first=stream.read(4)
        if len(first)!=4: raise ValueError('HDR_TRUNCATED')
        if 8<=w<=32767 and first[:2]==b'\x02\x02' and first[2]<128:
            if (first[2]<<8|first[3])!=w:raise ValueError('HDR_SCANLINE_INVALID')
            for ch in range(4):
                col=0
                while col<w:
                    flag=stream.read(1)
                    if not flag or flag[0]==0:raise ValueError('HDR_RLE_INVALID')
                    n=flag[0]-128 if flag[0]>128 else flag[0]
                    if col+n>w:raise ValueError('HDR_RLE_OVERFLOW')
                    part=stream.read(1 if flag[0]>128 else n)
                    if len(part)!=(1 if flag[0]>128 else n):raise ValueError('HDR_TRUNCATED')
                    raw[row,col:col+n,ch]=part[0] if flag[0]>128 else np.frombuffer(part,dtype='uint8');col+=n
        else:
            rest=stream.read(w*4-4)
            if len(rest)!=w*4-4:raise ValueError('HDR_TRUNCATED')
            raw[row]=np.frombuffer(first+rest,dtype='uint8').reshape(w,4)
    if stream.read(1):raise ValueError('HDR_TRAILING_BYTES')
    image=raw[:,:,:3].astype('float32')*np.exp2(raw[:,:,3].astype('float32')-136)[:,:,None]
    image[raw[:,:,3]==0]=0
    if not np.isfinite(image).all() or image.min()<0 or image.max()>max_value:raise ValueError('HDR_NUMERIC_RANGE_INVALID')
    return image

def loaded_latlong(image, offset, strength):
    import numpy as np
    return np.roll(np.flip(np.clip(image*strength,0,65504),axis=1),int(image.shape[1]*(180+angle(offset))/360),axis=1).copy()

class EnvironmentLibrary:
    def __init__(self, root, presets):
        self.root=Path(root)
        if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (self.root,*self.root.parents)):raise ValueError('UNSAFE_ENVIRONMENT_DIRECTORY')
        self.root.mkdir(parents=True,exist_ok=True)
        self.environments={p['id']:{**p,'source':{'kind':'bundled','license':'see existing provenance'},'thumbnail':'/api/environments/'+p['sha256']+'/thumbnail','contentId':p['sha256']} for p in presets}
        for p in self.root.glob('*.json'):
            v=json.loads(p.read_text(encoding='utf-8'));self.environments[v['id']]=v
    def safe_path(self,filename):
        if not re.fullmatch('[0-9a-f]{64}(?:\.original)?\.(?:hdr|json)',filename):raise ValueError('UNSAFE_ENVIRONMENT_FILENAME')
        path=self.root/filename
        if path.is_symlink() or getattr(path,'is_junction',lambda:False)():raise ValueError('UNSAFE_ENVIRONMENT_FILE')
        return path
    def import_bytes(self,data,name):
        image=decode_hdr(data);key=sha(data);derived=encode_hdr(image);dsha=sha(derived)
        if len(self.environments)>=67 and 'hdr-'+key not in self.environments:raise ValueError('ENVIRONMENT_LIBRARY_FULL')
        if sum(p.stat().st_size for p in self.root.glob('*.original.hdr'))+len(data)>256*1024*1024 and not self.safe_path(key+'.original.hdr').exists():raise ValueError('ENVIRONMENT_DISK_QUOTA')
        v={'id':'hdr-'+key,'name':text(name),'description':'本机导入，许可由使用者确认','sha256':key,'contentId':key,'derivedSha256':dsha,'hdr':key+'.hdr','index':0,'source':{'kind':'local-import','originalSha256':key,'format':'Radiance RGBE','color':'linear RGB; assumed sRGB primaries'},'width':image.shape[1],'height':image.shape[0],'min':float(image.min()),'max':float(image.max()),'bytes':len(data),'thumbnail':'/api/environments/'+key+'/thumbnail'}
        for filename,payload in ((key+'.original.hdr',data),(dsha+'.hdr',derived)):
            path=self.safe_path(filename)
            if path.exists() and path.read_bytes()!=payload:raise ValueError('CONTENT_COLLISION')
            path.write_bytes(payload)
        self.safe_path(key+'.json').write_text(json.dumps(v,ensure_ascii=False),encoding='utf-8');self.environments[v['id']]=v
        return v
    def derived(self,recipe):
        if recipe['mode']=='procedural':data=encode_hdr(synthesize(recipe))
        else:
            e=self.environments[recipe['environmentId']]
            if e['source']['kind']!='local-import':return None
            data=self.safe_path(e['derivedSha256']+'.hdr').read_bytes()
            if sha(data)!=e['derivedSha256']:raise ValueError('DERIVED_HDR_CHANGED')
        return data

def resolve_operations(current, operations, environments):
    """AI relative operations resolve ONLY against a trusted selected snapshot."""
    out=copy.deepcopy(current)
    if type(operations) is not list or not 1<=len(operations)<=8:raise ValueError('BOUNDED_OPERATIONS_REQUIRED')
    for op in operations:
        if not isinstance(op,dict):raise ValueError('OPERATION_REQUIRED')
        kind=op.get('op')
        if kind in ('rotate','exposure'):
            exact(op,('op','delta'));delta=number(op['delta'],-360 if kind=='rotate' else -4,360 if kind=='rotate' else 4)
            if kind=='rotate':out['offsetDeg']=angle(out['offsetDeg']+delta)
            else:out['strength']*=2**delta
        elif kind=='set':
            exact(op,('op','field','value'))
            if op['field'] not in ('offsetDeg','strength','ambient','mode','environmentId','environmentSha256'):raise ValueError('FIELD_NOT_ALLOWED')
            out[op['field']]=copy.deepcopy(op['value'])
        elif kind=='add_zone':
            exact(op,('op','zone'));out['zones'].append(copy.deepcopy(op['zone']))
        elif kind in ('edit_zone','remove_zone'):
            exact(op,('op','id','changes') if kind=='edit_zone' else ('op','id'))
            z=next((z for z in out['zones'] if z['id']==op['id']),None)
            if z is None:raise ValueError('UNKNOWN_ZONE')
            if kind=='remove_zone':out['zones'].remove(z)
            else:
                if not isinstance(op['changes'],dict) or not set(op['changes'])<=set(z)-{'id'}:raise ValueError('ZONE_FIELDS_INVALID')
                z.update(copy.deepcopy(op['changes']))
        else:raise ValueError('UNSUPPORTED_OPERATION')
    return normalize(out,environments)

def json_schema(environments):
    num=lambda lo,hi:{'type':'number','minimum':lo,'maximum':hi}
    obj=lambda props:{'type':'object','additionalProperties':False,'properties':props,'required':list(props)}
    col={'type':'string','pattern':'^#[0-9a-fA-F]{6}$'}
    ambient=obj({'strength':num(0,4),'color':col})
    zone=obj({'id':{'type':'string','pattern':'^[a-zA-Z0-9_-]{1,32}$'},'name':{'type':'string','minLength':1,'maxLength':40},'enabled':{'type':'boolean'},'azimuthDeg':num(-1e6,1e6),'elevationDeg':num(-90,90),'strength':num(0,16),'color':col,'sizeDeg':num(2,120)})
    recipe=obj({'schemaVersion':{'const':2},'mode':{'enum':['environment','procedural']},'environmentId':{'enum':[None,*environments]},'environmentSha256':{'enum':[None,*[e['sha256'] for e in environments.values()]]},'offsetDeg':num(-1e6,1e6),'strength':num(.25,4),'ambient':ambient,'zones':{'type':'array','maxItems':3,'items':zone},'synthesizerVersion':{'const':VERSION},'preprocessingVersion':{'const':PREPROCESS},'colorConvention':{'const':COLOR}})
    changes={**zone,'required':[]};changes['properties']={k:v for k,v in zone['properties'].items() if k!='id'}
    operations=[obj({'op':{'const':k},'delta':num(-360,360) if k=='rotate' else num(-4,4)}) for k in ('rotate','exposure')]
    operations += [obj({'op':{'const':'add_zone'},'zone':zone}),obj({'op':{'const':'edit_zone'},'id':zone['properties']['id'],'changes':changes}),obj({'op':{'const':'remove_zone'},'id':zone['properties']['id']})]
    operations += [obj({'op':{'const':'set'},'field':{'const':k},'value':v}) for k,v in recipe['properties'].items() if k in ('offsetDeg','strength','ambient','mode','environmentId','environmentSha256')]
    return {'oneOf':[recipe,obj({'operations':{'type':'array','minItems':1,'maxItems':8,'items':{'oneOf':operations}}})]}


def preprocessing_parameters(parameters):
    offset=number(parameters["offsetDeg"],-1e6,1e6);strength=number(parameters["strength"],.25,4)
    try:
        from experiments.controls import normalize as historic
        if parameters.get("schemaVersion")!=2:return historic(offset,strength)
    except ValueError:pass
    return {"offsetDeg":offset,"strength":strength,"envRot":180+offset,"envFlip":True,"rotateEnvlight":False,"logScale":10000,"version":PREPROCESS}
