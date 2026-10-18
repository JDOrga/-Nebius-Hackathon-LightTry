import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolveLanguage,translateString} from '../web/i18n.js';

test('explicit browser preference overrides browser languages; non-zh/en defaults to English',()=>{
 assert.equal(resolveLanguage(['en-US','zh-CN']),'en');
 assert.equal(resolveLanguage(['fr-FR','zh-TW','en-US']),'zh');
 assert.equal(resolveLanguage(['fr-FR']),'en');
 assert.equal(resolveLanguage(['en-US'],'zh'),'zh');
 assert.equal(resolveLanguage(['zh-CN'],'en'),'en');
});
test('translations preserve whitespace and do not rewrite user photo names',()=>{
 assert.equal(translateString(' 关闭中 ','en'),' Stopping ');
 assert.equal(translateString('最晚自动停机 00:59:59','en'),'Latest automatic stop 00:59:59');
 assert.equal(translateString('用Seedream重画图片 (8)','en'),'用Seedream重画图片 (8)');
 assert.equal(translateString('关闭中','zh'),'关闭中');
});
test('the workbench has an explicit local language selector without changing task identity',()=>{
 const html=readFileSync(new URL('../web/index.html',import.meta.url),'utf8');
 const source=readFileSync(new URL('../web/workbench.js',import.meta.url),'utf8');
 assert.ok(html.includes('id="locale-select"'));
 assert.ok(source.includes("import {installI18n,currentLanguage} from './i18n.js'"));
 assert.ok(!source.includes('navigator.language='));
});
