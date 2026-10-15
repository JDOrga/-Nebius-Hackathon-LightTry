import test from 'node:test';import assert from 'node:assert/strict';
import {allowed,createScheme,revise,variant,removeFamily,sameParameters,matchingTask,validateLibrary,referenceKey,restoreInputStub} from '../web/scheme-state.js';
const policy={approvedVariants:{sunny:[[0,.7],[45,1]]}};

test('deleting a family removes every version and selects the latest remaining plan for this photo',()=>{
 const a=createScheme('sunny','A','b'.repeat(32)),a2=revise(a,{...a.parameters,strength:.7});
 const b=variant(a,'B'),b2=revise(b,{...b.parameters,strength:.8});
 const other=createScheme('sunny','Other','c'.repeat(32));
 const library=[a,a2,b,b2,other],next=removeFamily(library,a.planId,a2,a.inputId,'sunny');
 assert.deepEqual(next.library,[b,b2,other]);assert.equal(next.current,b2);assert.equal(library.length,5);
});
test('deleting another variant preserves the edit cursor; deleting the last creates a valid replacement',()=>{
 const a=createScheme('sunny','A','b'.repeat(32)),b=variant(a,'B');
 assert.equal(removeFamily([a,b],b.planId,a,a.inputId,'sunny').current,a);
 const next=removeFamily([a],a.planId,a,a.inputId,'sunny');
 assert.equal(next.library.length,1);assert.equal(next.current.inputId,a.inputId);assert.notEqual(next.current.planId,a.planId);assert.equal(next.current.version,1);
});
test('closed dimensions and combinations are rejected',()=>{assert(allowed({environmentId:'sunny',offsetDeg:0,strength:.7},policy));assert(!allowed({environmentId:'sunny',offsetDeg:0,strength:1.4},policy));assert(!allowed({environmentId:'sunny',offsetDeg:45,strength:.7},policy));assert(!allowed({environmentId:'sunny',offsetDeg:0,strength:true},policy));});
test('edit creates lineage and clone creates independent family',()=>{const s=createScheme('sunny','A','b'.repeat(32));const n=revise(s,{...s.parameters,strength:.7});assert.equal(s.version,1);assert.equal(n.version,2);assert.equal(n.parentVersion,1);assert.equal(variant(s,'B').version,1);assert.notEqual(variant(s,'B').planId,s.planId);assert.notEqual(referenceKey(s,s.inputId),referenceKey(n,n.inputId));});
test('same preset is not enough for a result, wrong input cannot borrow',()=>{const task={taskId:'a',input:{id:'b'},status:'succeeded',expiresAt:Date.now()/1000+60,preset:{id:'scheme1',environmentId:'sunny',parameters:{offsetDeg:0,strength:1},recipeKey:'recipe'},result:{taskId:'a',inputId:'b',presetId:'scheme1',recipeKey:'recipe',parameters:{offsetDeg:0,strength:1}}};assert(matchingTask(task,'b',{environmentId:'sunny',offsetDeg:0,strength:1}));assert.equal(matchingTask(task,'b',{environmentId:'sunny',offsetDeg:0,strength:.7}),null);assert.equal(matchingTask(task,'different',{environmentId:'sunny',offsetDeg:0,strength:1}),null);task.executionUncertain=true;assert.equal(matchingTask(task,'b',{environmentId:'sunny',offsetDeg:0,strength:1}),null);});
test('legacy only maps to nominal default, without historical param fabrication',()=>{const t={taskId:'a',input:{id:'b'},status:'succeeded',expiresAt:Date.now()/1000+60,preset:{id:'sunny'},result:{taskId:'a',inputId:'b',presetId:'sunny'}};assert(matchingTask(t,'b',{environmentId:'sunny',offsetDeg:0,strength:1}));assert.equal(matchingTask(t,'b',{environmentId:'sunny',offsetDeg:45,strength:1}),null);});
test('library filters malformed data and preserves valid versions',()=>{const s=createScheme('sunny','A','b'.repeat(32));assert.equal(validateLibrary([s,{planId:'bad'}],['sunny']).length,1);assert(sameParameters(s.parameters,{...s.parameters}));});

test('changed recipe or normalized HDR binding cannot borrow task result',()=>{const t={taskId:'a',input:{id:'b'},status:'succeeded',expiresAt:Date.now()/1000+60,preset:{id:'x',environmentId:'sunny',recipeKey:'new',parameters:{offsetDeg:0,strength:1,hdrSha256:'new'}},result:{taskId:'a',inputId:'b',presetId:'x',recipeKey:'old',parameters:{offsetDeg:0,strength:1,hdrSha256:'old'}}};assert.equal(matchingTask(t,'b',{environmentId:'sunny',offsetDeg:0,strength:1}),null);});

test('unsubmitted input restore is identity-only, never stale blob or sample pixels',()=>{const stub=restoreInputStub({id:'a'.repeat(32),originalSha:'b'.repeat(64),name:'my photo',width:80,height:64,url:'blob:stale'});assert.equal(stub.needsFile,true);assert.equal(stub.url,undefined);assert.equal(stub.id,'a'.repeat(32));assert.equal(restoreInputStub({id:'bad'}),null);});

test('editing an old version never collides with an existing later version',()=>{const a=createScheme('sunny','A','b'.repeat(32));const b=revise(a,{...a.parameters,strength:.7});const c=revise(a,{...a.parameters,offsetDeg:45},a.name,[a,b]);assert.equal(c.version,3);assert.equal(c.parentVersion,1);assert.equal(b.parameters.strength,.7);});
