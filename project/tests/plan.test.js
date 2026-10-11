import test from 'node:test';
import assert from 'node:assert/strict';
import { createPlan, changePlan, undoPlan, invalidatePlan, beginRecommendation, applyRecommendation, failRecommendation, validResult, missingPresets } from '../web/plan.js';
import { languageService, serviceInference } from '../web/sources.js';
const allowed=['sunny','sunrise','street'];
const answer={status:'ready',presetIds:['sunrise','sunny'],reasons:['粉色晨光近似','日光氛围'],excludedIds:[],unsupported:[],question:''};

test('manual edit and one undo restore ordered recommendation and explanation',()=>{
  let p=applyRecommendation(beginRecommendation(createPlan(['sunny']),'a'),'a',answer,allowed);
  p=changePlan(p,['sunny']);assert.deepEqual(p.ids,['sunny']);
  p=undoPlan(p);assert.deepEqual(p.ids,answer.presetIds);assert.deepEqual(p.reasons,answer.reasons);
  assert.equal(undoPlan(p),p);
});
test('duplicate click is ignored; outdated reply or error cannot overwrite manual edits',()=>{
  let p=beginRecommendation(createPlan(['sunny']),'a');assert.equal(beginRecommendation(p,'b'),p);
  p=changePlan(p,['street']);assert.equal(applyRecommendation(p,'a',answer,allowed),p);
  assert.equal(failRecommendation(p,'a','old error'),p);
});
test('new photo invalidates pending text but preserves selection only',()=>{
  let p=beginRecommendation(createPlan(['sunrise']),'a');p=invalidatePlan(p);
  assert.deepEqual(p.ids,['sunrise']);assert.equal(p.busy,false);
  assert.equal(applyRecommendation(p,'a',answer,allowed),p);
  const s={upload:{id:'new'},tasks:{},task:null};assert.deepEqual(missingPresets(s,p.ids),p.ids);
});
test('failure, clarification and unsupported preserve chosen plan with honest messages',()=>{
  for(const value of [{...answer,status:'clarification',presetIds:[],reasons:[],question:'想要哪种氛围？'},
                      {...answer,status:'unsupported',presetIds:[],reasons:[],unsupported:['precision']}]) {
    const p=applyRecommendation(beginRecommendation(createPlan(['street']),'a'),'a',value,allowed);
    assert.deepEqual(p.ids,['street']);assert.equal(p.busy,false);
  }
  const p=failRecommendation(beginRecommendation(createPlan(['sunny']),'a'),'a','未配置');
  assert.deepEqual(p.ids,['sunny']);assert.equal(p.error,'未配置');
});
test('frontend rejects malformed and arbitrary IDs without changing selection',()=>{
  for(const value of [null,{}, {...answer,presetIds:['shell']}, {...answer,command:'exec'}, {...answer,presetIds:['sunny','sunny']}, {...answer,reasons:['x'.repeat(181),'y']}]) {
    const p=applyRecommendation(beginRecommendation(createPlan(['street']),'a'),'a',value,allowed);
    assert.deepEqual(p.ids,['street']);assert.ok(p.error);
  }
});
test('only matching unexpired validated result removes a preset from explicit generation',()=>{
  const task={taskId:'t',input:{id:'i'},status:'partial',expiresAt:Date.now()/1000+100,
    presetResults:{sunny:{status:'succeeded',result:{taskId:'t',inputId:'i',presetId:'sunny'}}}};
  const s={upload:{id:'i'},task,tasks:{}};
  assert.equal(validResult(s,'sunny'),task);assert.deepEqual(missingPresets(s,allowed),['sunrise','street']);
  assert.equal(validResult({...s,upload:{id:'other'}},'sunny'),null);
  assert.equal(validResult(s,'sunny',Date.now()+200000),null);
  task.presetResults.sunny.result.presetId='street';assert.equal(validResult(s,'sunny'),null);
});
test('recommendation sends text and bounded current plan only, never calls task submit',async()=>{
  const oldFetch=globalThis.fetch, oldSubmit=serviceInference.submit;let calls=[];
  serviceInference.submit=()=>assert.fail('recommendation started generation');
  globalThis.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>answer};};
  try {
    assert.deepEqual(await languageService.recommend('warm',{presetIds:['sunny'],excludedIds:[]},false),answer);
    assert.equal(calls.length,1);assert.equal(calls[0].url,'/api/language/recommend');
    assert.deepEqual(Object.keys(JSON.parse(calls[0].options.body)),['text','currentPlan','compareThree']);
  } finally {globalThis.fetch=oldFetch;serviceInference.submit=oldSubmit;}
});
