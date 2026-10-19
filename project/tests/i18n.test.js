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
test('English workbench translates chat and pending-photo UI copy without rewriting model text',()=>{
 const cases=new Map([
  ['文字响应已返回。 未自动应用或生成。','Text response received. No settings were applied and no image was generated.'],
  ['正在等待回复；收起或关闭面板不会取消请求。','Waiting for a reply; collapsing or closing this panel will not cancel the request.'],
  ['待生成 · 仅显示输入','Pending generation · input only'],
  ['当前方案尚未生成。','The current plan has not been generated yet.'],
  ['我的照片 · 本机草稿','My photo · local draft'],
  ['草稿 / 待生成','Draft / pending generation'],
 ]);
 for(const [source,english] of cases){assert.equal(translateString(source,'en'),english);assert.equal(translateString(source,'zh'),source);}
 const modelReply='在原有的自然日光环境基础上，加入暖色主光。';
 assert.equal(translateString(modelReply,'en'),modelReply);
 const chat=readFileSync(new URL('../web/chat.js',import.meta.url),'utf8');
 assert.ok(chat.includes('replyLanguage:currentLanguage()'));
 assert.ok(!chat.includes("replyLanguage:'zh'"));
});
test('generated lighting summaries and appended GPU notices translate without changing state claims',()=>{
 assert.equal(translateString('晴日公园 / 默认光照 · v1','en'),'Sunny park / Default lighting · v1');
 assert.equal(translateString('实验性程序化布光 / 0° / HDR ×1 · v2','en'),'Experimental procedural lighting / 0° / HDR ×1 · v2');
 const notice='Stop was requested by the operator. STOPPED and an empty instance list are confirmed. A new start requires a manual action. 当前快照已过期。 工作台在线连接已断开，正在重连。连续5分钟没有任何工作台连接会自动停机；恢复连接不会自动开机。';
 assert.equal(translateString(notice,'en'),'Stop was requested by the operator. STOPPED and an empty instance list are confirmed. A new start requires a manual action. Current snapshot is stale. The workbench connection was lost and is reconnecting. Five minutes without any workbench connection triggers automatic stop; reconnecting does not restart the GPU.');
 assert.equal(translateString(notice,'zh'),notice);
});
