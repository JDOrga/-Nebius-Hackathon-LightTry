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
 assert.ok(source.includes("import {installI18n,currentLanguage,translateString} from './i18n.js'"));
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
test('English chat application and context notices have no Chinese UI text',()=>{
 const cases=new Map([
  ['编辑上下文已改变，下一次请求使用当前版本。旧建议不能直接应用。','The editing context changed. The next request will use the current version. The old suggestion cannot be applied directly.'],
  ['已应用到 v2，尚未生成。','Applied to v2; not generated yet.'],
  ['已应用到版本 2，尚未生成。','Applied to version 2; not generated yet.'],
  ['当前方案已确认应用到 v2；尚未生成。','Applied to current plan v2; not generated yet.'],
  ['当前方案已确认应用到 v2；已有匹配结果。','Applied to current plan v2; a matching result already exists.'],
  ['已确认应用到 v2；未由此操作提交生成。','Applied to v2; this action did not submit generation.'],
 ]);
 for(const [source,expected] of cases){assert.equal(translateString(source,'en'),expected);assert.equal(translateString(source,'zh'),source);}
});
test('generation confirmation translates a built-in plan label without rewriting a custom name',()=>{
 assert.equal(translateString('当前方案：光照方案 · v3','en'),'Current plan: Lighting plan · v3');
 assert.equal(translateString('新方案待生成：光照方案 · v3（仅此方案）。','en'),
  'New plan pending generation: Lighting plan · v3 (this plan only).');
 assert.equal(translateString('新方案待生成：用户自定义名字 · v3（仅此方案）。','en'),
  'New plan pending generation: 用户自定义名字 · v3 (this plan only).');
});
test('English controlled status, recovery, library and monitor samples have no Chinese remnants',()=>{
 const controlled=[
  '准备期间上下文已改变，尚未发送模型请求。','响应关联身份不一致，未应用。','等待超时，服务可能仍在处理或已计费，不会自动重试。',
  '分析照片 · 阶段 1/4','模拟 · 生成光照效果 · 阶段 2/4，本阶段百分比未知','离线演示 · 非真实 GPU',
  '状态不可靠 · 最近观测 2026/10/19 17:00 · 5 秒前','状态不可靠 · 尚无可靠观测',
  '方案编号 abcdef12 / v2','正在准备生成','正在分析照片；执行状态不确定，禁止重复提交',
  '历史生成结果 · 2026/10/19 17:00 · 非本次生成','正式任务 abcdef12 · 原生成已取回，未重算 · 源方案版本 2',
  '离线模拟任务 · 非模型结果 abcdef12 · 源方案版本 旧固定预设','历史样例 2026-10-19',
  '取回失败 · 可恢复 · 实验性','GPU状态无法确认','暂时无法读取 GPU 状态；下列旧快照不代表当前状态。',
  '请重新选择此方案使用的原照片。','此旧方案无法自动核对原照片，请确认所选文件正确后继续。',
  '保存全部方案到服务；若当前为用户照片，会上传原照片到私有数据目录。不会生成或收费。继续？',
  '需要 v1 方案库 JSON。','方案库含无效版本；未部分导入。',
 ];
 for(const source of controlled){assert.doesNotMatch(translateString(source,'en'),/[\u3400-\u9fff]/u,source);assert.equal(translateString(source,'zh'),source);}
 const userName='我自己的照片';assert.equal(translateString(userName,'en'),userName);
 assert.equal(translateString(`${userName} · AI变体`,'en'),`${userName} · AI variant`);
 const console=readFileSync(new URL('../web/console.js',import.meta.url),'utf8');
 const workbench=readFileSync(new URL('../web/workbench.js',import.meta.url),'utf8');
 const chat=readFileSync(new URL('../web/chat.js',import.meta.url),'utf8');
 assert.match(console,/currentLanguage\(\)==='en'\?'New light zone'/);
 assert.match(console,/currentLanguage\(\)==='en'\?'Parameter is out of range'/);
 assert.equal((workbench.match(/confirm\(translateString\(/g)||[]).length,2);
 assert.match(chat,/child\.setAttribute\('data-no-i18n',''\)/);
 assert.match(chat,/m\.role==='user'\)bubble\.setAttribute\('data-no-i18n',''\)/);
});
test('English UI dictionary has no duplicate source keys',()=>{
 const source=readFileSync(new URL('../web/i18n-en.js',import.meta.url),'utf8');
 const keys=[...source.matchAll(/^\s*\['((?:\\.|[^'\\])*)','/gm)].map(match=>match[1]);
 assert.ok(keys.length>500);
 assert.equal(keys.length,new Set(keys).size);
});
