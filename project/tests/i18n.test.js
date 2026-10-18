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
test('new failure and verified reset messages translate without changing the task identity',()=>{
 const id='a'.repeat(32);
 assert.match(translateString(`生成失败：上传到 GPU 服务器超时；执行状态仍待核实，禁止重复提交。请查看 GPU 状态并核实停止释放。 任务编号：${id}.`,'en'),/Upload to the GPU server timed out.*Do not resubmit.*Task ID: a{32}/);
 assert.match(translateString(`生成失败：上传回执未确认；本次无结果，状态已核实。不会自动重试；如需再次生成，请重新明确确认。 任务编号：${id}.`,'en'),/Upload acknowledgment unconfirmed.*No automatic retry.*Task ID: a{32}/);
});
test('the workbench has an explicit local language selector without changing task identity',()=>{
 const html=readFileSync(new URL('../web/index.html',import.meta.url),'utf8');
 const source=readFileSync(new URL('../web/workbench.js',import.meta.url),'utf8');
 assert.ok(html.includes('id="locale-select"'));
 assert.ok(source.includes("import {installI18n,currentLanguage} from './i18n.js'"));
 assert.ok(!source.includes('navigator.language='));
});
