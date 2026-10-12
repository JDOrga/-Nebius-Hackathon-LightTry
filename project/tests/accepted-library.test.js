import test from 'node:test';import assert from 'node:assert/strict';
import {mergeAcceptedLibrary,schemePresentation,validateLibrary,schemeWire} from '../next/web/scheme-state.js';
const imported={schemaVersion:1,planId:'a'.repeat(32),version:1,name:'AI · 2026-10-12实测',inputId:'b'.repeat(32),parameters:{schemaVersion:2,mode:'procedural',environmentId:null,offsetDeg:0,strength:1},importedResultSha256:'c'.repeat(64),provenance:{caseId:'AI'}};
test('idempotent import preserves user library',()=>{const user={...structuredClone(imported),planId:'d'.repeat(32),name:'我的方案'};const once=mergeAcceptedLibrary([user],[imported]);assert.equal(once.length,2);assert.deepEqual(mergeAcceptedLibrary(once,[imported]),once);assert.equal(once[0].name,'我的方案');assert.equal(validateLibrary(once,['sunny']).length,2)});
test('identity collision fails without overwriting',()=>{const wrong={...structuredClone(imported),inputId:'f'.repeat(32)};assert.throws(()=>mergeAcceptedLibrary([wrong],[imported]),/身份冲突/);assert.equal(wrong.inputId,'f'.repeat(32))});
test('capacity does not destroy existing library',()=>{const list=Array.from({length:200},(_,i)=>({...imported,planId:String(i).padStart(32,'0')}));assert.throws(()=>mergeAcceptedLibrary(list,[imported]),/已满/);assert.equal(list.length,200)});
test('AI import stays visibly AI; personal rename preserved',()=>{assert.equal(schemePresentation(imported).title,'AI · 10-12实测');assert.equal(schemePresentation({...imported,name:'我自己的名字'}).title,'我自己的名字')});

test('wire schema strips provenance only, retaining full lighting parameters',()=>{const s=schemeWire(imported);assert.equal(Object.keys(s).length,7);assert.deepEqual(s.parameters,imported.parameters);assert(!('provenance' in s));assert(!('importedResultSha256' in s));});
