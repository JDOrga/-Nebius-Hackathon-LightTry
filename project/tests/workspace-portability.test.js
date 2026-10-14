import test from 'node:test';
import assert from 'node:assert/strict';
import {archive,readArchive,mergeLibraries} from '../web/workspace-portability.js';
import {createScheme} from '../web/scheme-state.js';

test('migration preserves literal identities, names and versions without photo bytes or credentials',()=>{
 const s=createScheme('sunny','用户完整名称','a'.repeat(32));
 const p={id:s.inputId,name:'原照片',width:64,height:64,originalSha:'b'.repeat(64),url:'blob:private',apiKey:'DO_NOT_EXPORT',pixels:'private'};
 const value=archive([s],[p],['c'.repeat(32)]),text=JSON.stringify(value);
 assert(!text.includes('blob:'));assert(!text.includes('DO_NOT_EXPORT'));assert(!text.includes('pixels'));
 assert.deepEqual(readArchive(value,['sunny']).schemes,[s]);
 assert.equal(value.photos[0].originalSha,p.originalSha);
});
test('legacy raw library import and merge are idempotent, not silent overwrites',()=>{
 const s=createScheme('sunny','旧浏览器','a'.repeat(32));
 assert.deepEqual(readArchive([s],['sunny']).schemes,[s]);
 assert.equal(mergeLibraries([s],[s]).length,1);
 assert.throws(()=>mergeLibraries([s],[{...s,name:'替换'}]),/冲突/);
 assert.throws(()=>readArchive({schemaVersion:1,schemes:[s,{bad:true}]},['sunny']),/未部分导入/);
});
