"""Local evidence/review gate for the five-forward calibration; never network/GPU."""
import copy
import hashlib
import html
import json
from pathlib import Path
from inference.jobs import atomic, read
from runtime.layout import packet_runtime_file
from runtime.joint import changes
from runtime.joint_results import validate_case

VERSION = 'direction-energy-calibration-five-v2'
IDS = ['C-repeat', 'direction-225', 'direction-315', 'width-45', 'width-70']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bind_references(package):
    """Bind immutable local historical artifacts; they are NOT in the upload."""
    plan = read(package/'packet/joint.json'); references = []
    for case in plan['cases']:
        if case['id'] not in ('B', 'C'): continue
        result = validate_case(package/'packet', package/'execution/results', case)
        directory = package/'execution/results/cases'/case['id']
        paths = {'frame': result['path'], 'condition': str(directory/'condition.json'),
                 'modelCondition': str(directory/'model-condition.json'),
                 'complete': str(directory/'0/complete.json'),
                 'configuration': str(package/'execution/results/configuration.json'),
                 'plan': str(package/'packet/joint.json')}
        for name in ('joint_worker.py','joint_entry.py','joint.py','entry.py'):
            paths['code-'+name]=str(packet_runtime_file(package/'packet', name))
        references.append({'caseId': case['id'], 'parameters': case['parameters'],
            'recipeKey': case['recipeKey'], 'hdrSha256': case['hdrSha256'],
            'outputSha256': result['sha256'], 'paths': paths,
            'hashes': {k: sha(v) for k, v in paths.items()}, 'cohort': 'historical 2026-10-12'})
    if [r['caseId'] for r in references] != ['B', 'C']: raise ValueError('HISTORICAL_B_C_REQUIRED')
    return references


def prepare_review(packet, output):
    from PIL import Image, ImageDraw
    root = Path(__file__).resolve().parents[2]
    source = root/'controlled-tests/20261007-four-materials/prepared_inputs.json'
    p = read(source)['images'][0]
    rois = p['derived_roi_xyxy']
    # Reuse the archived preselected polygon, NOT a rectangle selected on outputs.
    review = {'status': 'prepared-not-run', 'coordinateSystem': 'normalized full 1280x704 image',
        'source': str(source), 'sourceSha256': sha(source),
        'rectanglesPixels': rois, 'rectanglesNormalized': {k: [v[0]/1280,v[1]/704,v[2]/1280,v[3]/704] for k,v in rois.items()},
        'subjectMaskPolygonPixels': p['interior_mask_derived_polygon'],
        'subjectMaskPolygonNormalized': [[x/1280,y/704] for x,y in p['interior_mask_derived_polygon']],
        'subjectMaskSha256': p['interior_mask_sha256'],
        'shadowROI': 'bottom_contact', 'subjectROI': 'surface_texture intersect original interior polygon',
        'auxiliaryCentroidThresholdROIWidth': .08,
        'noAutomaticVisualPass': True, 'noOutputBrightnessNormalization': True}
    atomic(output/'roi.json', review)
    im = Image.open(p['derived_path']).convert('RGB'); draw = ImageDraw.Draw(im)
    for name, box in rois.items():
        draw.rectangle(box, outline='red', width=3);draw.text((box[0],box[1]),name,fill='red')
    draw.line([tuple(v) for v in p['interior_mask_derived_polygon']]+[tuple(p['interior_mask_derived_polygon'][0])],fill='cyan',width=3)
    im.save(output/'roi-overlay.png')
    atomic(output/'visual-review-template.json', {
        'historicalBaseline': {'visual': 'pending', 'identityAudit': 'pending', 'rngAudit': 'pending', 'driftExplanation': ''},
        'direction': {'verdict': 'pending', 'subjectDistribution': '', 'occlusion': '', 'highlights': '', 'castShadow': '', 'reason': ''},
        'width': {'verdict': 'pending', 'currentIdentityAudit': 'pending', 'highlights': '', 'shadowEdges': '', 'reason': ''},
        'choices': ['pass','fail','uncertain'], 'noPhysicalSoftnessPass': True})


def pixel_difference(a, b):
    import numpy as np
    from PIL import Image
    x = np.asarray(Image.open(a).convert('RGB'), dtype='int16');y = np.asarray(Image.open(b).convert('RGB'), dtype='int16')
    if x.shape != y.shape: raise ValueError('BASELINE_DECODE_SHAPE_MISMATCH')
    d = np.abs(x-y)
    return {'historicalSha256': sha(a), 'currentSha256': sha(b), 'fileEqual': sha(a)==sha(b),
            'decodedPixelsEqual': bool((d==0).all()), 'mae8bit': float(d.mean()),
            'maxDelta8bit': int(d.max()), 'changedPixelFraction': float((d!=0).any(axis=2).mean())}


def roi_metrics(frame, roi):
    import numpy as np
    from PIL import Image, ImageDraw
    im = Image.open(frame).convert('RGB');x = np.asarray(im,dtype='float64')/255
    luminance = x @ np.array([.2126,.7152,.0722])
    mask = Image.new('L',im.size);ImageDraw.Draw(mask).polygon([tuple(v) for v in roi['subjectMaskPolygonPixels']],fill=255)
    region = np.asarray(mask)>0;box=roi['rectanglesPixels']['surface_texture'];rect=np.zeros(region.shape,dtype=bool)
    rect[box[1]:box[3],box[0]:box[2]]=True;region &= rect
    values = luminance[region];cut=float(np.quantile(values,.75))
    bright=region & (luminance>=cut); yy,xx=np.nonzero(bright)
    return {'centroidNormalizedImage': [float(xx.mean()/1280),float(yy.mean()/704)],
            'subjectMeanDisplayLuma': float(values.mean()),'subjectP25DisplayLuma':float(np.quantile(values,.25)),
            'highlightCoverageAboveDisplayLuma08':float((values>=.8).mean()),
            'centroidROIWidthPixels':box[2]-box[0], 'auxiliaryOnly':True,
            'shadowEdge': 'manual assessment in fixed bottom_contact ROI; not an automatic physical metric'}


def identity_audit(packet, root):
    plan=read(packet/'joint.json');historical=next(r for r in plan['historicalReferences'] if r['caseId']=='C')
    old=read(Path(historical['paths']['plan']));old_complete=read(Path(historical['paths']['complete']))
    case=plan['cases'][0];current=read(root/'cases/C-repeat/0/complete.json')
    before=old_complete['identity'];after=current['identity']
    # Exact recorded identities contain model/config/upstream/seed/inverse/input.
    stripped=lambda d:{k:v for k,v in d.items() if k not in ('joint','jointPlanKey','case','taskId','nonce')}
    old_cond=read(Path(historical['paths']['condition']));new_cond=read(root/'cases/C-repeat/condition.json')
    old_model=read(Path(historical['paths']['modelCondition']));new_model=read(root/'cases/C-repeat/model-condition.json')
    return {'inputEqual':plan['input']==old['input'],'inverseEqual':plan['inverseSource']==old['inverseSource'],
        'runConfigEqual':plan['runConfig']==old['runConfig'], 'recipeEqual':case['parameters']==historical['parameters'],
        'actualHDREqual':case['hdrSha256']==historical['hdrSha256']==old_cond['hdrSha256']==new_cond['hdrSha256'],
        'baseIdentityDiff':changes(stripped(before),stripped(after)),
        'modelConditionDiff':changes(old_model,new_model),
        'conditionFieldDiff':changes(old_cond['fields'],new_cond['fields']),
        'codeVersions':{n:{'historicalSha256':historical['hashes']['code-'+n],
            'currentSha256':sha(packet_runtime_file(packet, n))} for n in ('joint_worker.py','joint_entry.py','joint.py','entry.py')},
        'rngPolicyHistorical':old_complete.get('randomPolicy'), 'rngPolicyCurrent':current.get('randomPolicy'),
        'sameSeedDoesNotGuaranteeByteEquality':True}


def finalize(package, review_path=None):
    packet=package/'packet';plan=read(packet/'joint.json');root=package/'execution/results';job=package/'execution'
    if plan['version']!=VERSION: raise ValueError('FIVE_CALIBRATION_REQUIRED')
    refs=plan['historicalReferences']
    for ref in refs:
        for k,p in ref['paths'].items():
            if sha(p)!=ref['hashes'][k]:raise ValueError('HISTORICAL_EVIDENCE_CHANGED')
    completed={}
    for case in plan['cases']:
        if (root/'cases'/case['id']/'0/complete.json').exists():completed[case['id']]=validate_case(packet,root,case)
    event=read(root/'execution.json')
    events=[json.loads(line) for line in (root/'forward-timing.jsonl').read_text(encoding='utf-8').splitlines()] if (root/'forward-timing.jsonl').exists() else []
    counts=[v for v in events if v.get('event')=='joint_complete']
    resets=[v.get('caseId') for v in events if v.get('event')=='calibration_rng_reset']
    counts_ok=len(counts)==1 and (counts[0]['initializationCount'],counts[0]['forwardCount'],counts[0]['inverseCount'])==(1,5,0) and resets==IDS
    terminal_ok=event.get('status')=='succeeded' and event.get('executionStopped') is True
    ready=len(completed)==5 and counts_ok and terminal_ok
    roi=read(package/'roi.json');review=read(review_path) if review_path else read(package/'visual-review-template.json')
    for group,field in (('historicalBaseline','visual'),('direction','verdict'),('width','verdict')):
        if review[group][field] not in ('pending','pass','fail','uncertain'):raise ValueError('INVALID_VISUAL_REVIEW')
    for group,fields in (('direction',('subjectDistribution','occlusion','highlights','castShadow','reason')),
                         ('width',('highlights','shadowEdges','reason'))):
        if review[group]['verdict']!='pending' and not all(type(review[group].get(f)) is str and review[group][f].strip() for f in fields):
            raise ValueError('MANUAL_MULTI_CUE_REVIEW_REQUIRED')
    old_workbench=read(job/'summary.json').get('workbench') if (job/'summary.json').exists() else None
    report={'execution':'generated-five' if ready else 'partial-or-unverified', 'structure':'passed' if ready else 'partial',
        'visual':'pending', 'workbench':(old_workbench or 'ready-for-explicit-import') if ready else 'not-ready',
        'observedCounts':counts, 'independentRNGResetCases':resets,
        'completed':list(completed), 'direction':'pending', 'width':'pending', 'review':review,
        'historicalBaseline':None,'identityAudit':None,'noAdditionalForwards':True,'noPhysicalSoftnessClaim':True}
    if 'C-repeat' in completed:
        c=next(r for r in refs if r['caseId']=='C')
        report['historicalBaseline']=pixel_difference(c['paths']['frame'],completed['C-repeat']['path'])
        report['identityAudit']=identity_audit(packet,root)
        drift=review['historicalBaseline']['visual'];audit=report['identityAudit']
        identity_ok=all(audit[k] for k in ('inputEqual','inverseEqual','runConfigEqual','recipeEqual','actualHDREqual')) and not any(audit[k] for k in ('baseIdentityDiff','modelConditionDiff','conditionFieldDiff'))
        historical_ok=identity_ok and drift=='pass' and review['historicalBaseline']['identityAudit']=='pass' and review['historicalBaseline']['rngAudit']=='pass'
        report['historicalComparable']=historical_ok
        report['direction']='paused-historical-baseline-audit' if not historical_ok else review['direction']['verdict']
        width_ok=all(n in completed for n in ('C-repeat','width-45','width-70'))
        base_marker=read(root/'cases/C-repeat/0/complete.json')
        base_identity={k:v for k,v in base_marker['identity'].items() if k not in ('joint','jointPlanKey','case','taskId','nonce')}
        base_model=read(root/'cases/C-repeat/model-condition.json')
        width_differences={}
        for n in ('width-45','width-70'):
            if n not in completed:continue
            marker=read(root/'cases'/n/'0/complete.json');model=read(root/'cases'/n/'model-condition.json')
            stripped={k:v for k,v in marker['identity'].items() if k not in ('joint','jointPlanKey','case','taskId','nonce')}
            diff=changes(base_identity,stripped);normal_diff=changes(base_model['env_nrm'],model['env_nrm'])
            width_differences[n]={'baseIdentityDiff':diff,'normalConditionDiff':normal_diff}
            width_ok &= not diff and not normal_diff and marker.get('randomPolicy')==base_marker.get('randomPolicy')
        report['currentWidthIdentityAudit']={'comparable':bool(width_ok),'differences':width_differences,'independentOfHistoricalDrift':True}
        report['width']=review['width']['verdict'] if width_ok and review['width']['currentIdentityAudit']=='pass' else 'pending-current-cohort-identity'
        report['metrics']={name:roi_metrics(v['path'],roi) for name,v in completed.items()}
        center=report['metrics']['C-repeat']['centroidNormalizedImage'][0]
        for name,metrics in report['metrics'].items():
            metrics['centroidShiftROIWidthFraction']=abs(metrics['centroidNormalizedImage'][0]-center)*1280/metrics['centroidROIWidthPixels']
        for name,record in completed.items():
            from PIL import Image,ImageDraw
            im=Image.open(record['path']).convert('RGB');d=ImageDraw.Draw(im)
            for box in roi['rectanglesPixels'].values():d.rectangle(box,outline='red',width=3)
            d.line([tuple(v) for v in roi['subjectMaskPolygonPixels']]+[tuple(roi['subjectMaskPolygonPixels'][0])],fill='cyan',width=3)
            im.save(job/(name+'-roi.png'))
        if report['direction']!='pending' and report['width'] not in ('pending','pending-current-cohort-identity'):
            report['visual']='reviewed-with-limitations'
    atomic(job/'calibration-summary.json',report)
    prior=read(job/'summary.json') if (job/'summary.json').exists() else {}
    atomic(job/'summary.json',{**prior,'execution':report['execution'],'structure':report['structure'],
        'visual':report['visual'],'workbench':prior.get('workbench',report['workbench']) if ready else 'not-ready','calibrationSummary':'calibration-summary.json'})
    comparison_page(packet,job/'comparison.html',root,report)
    return report


def stage_import(package):
    """Reuse the verified additive studio loader; do not pretend a browser merged."""
    from accepted import load_accepted_many
    import shared_http as server
    root=Path(__file__).resolve().parents[2]
    historical=root/'.local/lighttry-joint-20261012/ai-confirmed-package'
    catalog=server.load_catalog(root/'.local/demo-candidate-20261010/demo-assets')
    a,b,c=load_accepted_many([historical,package],catalog)
    again=load_accepted_many([historical,package,package],catalog)
    if (a,b,c)!=again:raise ValueError('ADDITIVE_IMPORT_NOT_IDEMPOTENT')
    job=package/'execution'
    atomic(job/'workbench-import.json',{'status':'verified-import-data-ready; live-studio-not-loaded',
        'packages':[str(historical),str(package)],'schemes':c,'photoRecipeOutputIdentityVerified':True,
        'repeatIdempotent':True,'historyOrUserSchemesOverwritten':False})
    for name in ('summary.json','calibration-summary.json'):
        v=read(job/name);v['workbench']='verified-import-data-ready; live-studio-not-loaded';atomic(job/name,v)


def comparison_page(packet,target,root=None,report=None):
    plan=read(packet/'joint.json');sections=[]
    for ref in plan.get('historicalReferences',[]):
        sections.append('<section><h2>历史 '+ref['caseId']+' · 2026-10-12（不是本轮）</h2><img width="600" src="'+html.escape(Path(ref['paths']['frame']).as_uri())+'"><pre>'+html.escape(json.dumps(ref['parameters'],ensure_ascii=False,indent=2))+'</pre><p>'+ref['outputSha256']+'</p></section>')
    for case in plan['cases']:
        result=None
        if root and (root/'cases'/case['id']/'0/complete.json').exists():result=validate_case(packet,root,case)
        sections.append('<section><h2>本轮 '+case['id']+' · '+('已生成；视觉需独立判定' if result else '尚未运行')+'</h2>'+('<img width="600" src="'+html.escape(Path(result['path']).as_uri())+'">' if result else '')+'<pre>'+html.escape(json.dumps(case['parameters'],ensure_ascii=False,indent=2))+'</pre><p>recipeKey '+case['recipeKey']+'; output '+(result['sha256'] if result else '未生成')+'</p></section>')
    target.write_text('<!doctype html><meta charset="utf-8"><title>五项校准对照</title><style>body{font:16px sans-serif;max-width:1400px;margin:auto}section{border:1px solid #aaa;padding:16px;margin:16px}img{max-width:100%}</style><h1>历史 B/C + 本轮五项</h1><p>ROI质心8%仅辅助；主体明暗/遮挡/高光/投影阴影需人工综合判断。仅本图当前管线粗方位，不是任意照片准确左/右。相同seed不保证逐字节相同。历史漂移未解释则暂停历史方向结论；当轮C-repeat/width组另判。发射球面积积分受控不保证物体能量或最终亮度相同；不归一化输出，不宣称物理柔光验证通过。</p>'+('<pre>'+html.escape(json.dumps(report,ensure_ascii=False,indent=2))+'</pre>' if report else '')+''.join(sections),encoding='utf-8')
