import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {inferenceProgress,paintGenerationButton,consoleView,paintGpuConsole} from '../web/gpu-monitor.js';
const source=readFileSync(new URL('../web/workbench.js',import.meta.url),'utf8');
const html=readFileSync(new URL('../web/index.html',import.meta.url),'utf8');
const css=readFileSync(new URL('../web/workbench.css',import.meta.url),'utf8');
class Node{
 constructor(document){this.ownerDocument=document;this.dataset={};this.style={};this.attrs={};this.children=[];this.textContent='';this.classes=new Set();this.classList={toggle:(n,on)=>on?this.classes.add(n):this.classes.delete(n)};}
 setAttribute(name,value){this.attrs[name]=String(value)}
 removeAttribute(name){delete this.attrs[name]}
 replaceChildren(...children){this.children=children}
 append(...children){this.children.push(...children)}
}
function dom(){const nodes=new Map();const d={createElement:()=>new Node(d),getElementById:id=>{if(!nodes.has(id))nodes.set(id,new Node(d));return nodes.get(id)}};return d;}
const task=stage=>({status:'running',stage,executionUncertain:false});
test('upload queued preflight and weights do not pretend inference started',()=>{
 for(const value of [null,{status:'queued',stage:'inverse'},task('weights'),task('preflight')])assert.equal(inferenceProgress(value),null);
 const d=dom(),button=d.getElementById('generate');paintGenerationButton(button,{status:'queued'});
 assert.equal(button.textContent,'等待推理接收');assert.equal(button.attrs.role,undefined);
});
test('actual inference renders disabled indeterminate progressbar, not guessed percentages',()=>{
 const d=dom(),button=d.getElementById('generate');paintGenerationButton(button,task('inverse'));
 assert.equal(button.attrs.role,'progressbar');assert.equal(button.disabled,true);assert.equal(button.attrs['aria-valuenow'],undefined);
 assert.match(button.attrs['aria-valuetext'],/分析照片.*1\/4.*百分比未知/);assert.equal(button.children.length,3);
 assert.equal(button.children[2].children[0].style.width,'0%');assert.equal(button.children[2].children[1].style.width,'25%');
 assert.equal(button.classes.has('generation-progress'),true);
});
test('phase progress follows server events and never increases by elapsed time',()=>{
 assert.deepEqual(['inverse','forward','validating','transferring'].map(s=>inferenceProgress(task(s)).ordinal),[1,2,3,4]);
 const value=inferenceProgress(task('inverse'));assert.equal(value.percent,null);
 assert.deepEqual(inferenceProgress(task('inverse')),value);
});
test('uncertain stale and terminal tasks cannot keep an active progressbar',()=>{
 const d=dom(),button=d.getElementById('generate');paintGenerationButton(button,task('inverse'));
 paintGenerationButton(button,{...task('inverse'),executionUncertain:true});assert.equal(button.attrs.role,undefined);assert.match(button.textContent,/待核实/);
 paintGenerationButton(button,{...task('forward'),progressStale:true});assert.match(button.textContent,/暂不可用/);
 for(const status of ['succeeded','failed','expired','partial'])assert.equal(inferenceProgress({...task('inverse'),status}),null);
 button.textContent='结果已就绪';paintGenerationButton(button,null);assert.equal(button.textContent,'结果已就绪');assert.equal(button.classes.has('generation-progress'),false);
});
test('simulation has an explicit label and no generation call in the view module',()=>{
 const d=dom(),button=d.getElementById('generate');paintGenerationButton(button,task('forward'),{simulation:true});assert.match(button.attrs['aria-label'],/^模拟/);
 const view=readFileSync(new URL('../web/gpu-monitor.js',import.meta.url),'utf8');assert(!view.includes('fetch('));assert(!view.includes('setInterval('));
});
const info=(now=100)=>({state:'LOADING',observedAt:now,simulation:true,budgetUsdIncludingTax:3,
 monitor:{workerStale:false,providerState:'RUNNING',host:{vmId:'VM_FIXTURE',ip:'127.0.0.1'},worker:{modelLoaded:false,modelState:'loading',loadingProgress:{phases:[
 {phase:'inverse',state:'loading',activeStage:'checkpoint_read',completedStages:['module_import'],elapsedMs:1000},
 {phase:'forward',state:'loading',activeStage:'network_setup',completedStages:[]}]}}}});
test('console shows truthful summary, two phase stages and unknown hardware metrics',()=>{
 const view=consoleView(info(),105);assert.equal(view.title,'正在准备模型');assert.equal(view.model,'正在加载');assert.equal(view.budget,'$3.00 含税');
 assert.equal(view.phases[0].active,'读取主模型权重');assert.equal(view.phases[0].completed,1);assert.equal(view.phases[0].read,'未采集');
 assert(view.details.some(([key,value])=>key.includes('利用率')&&value.includes('未接入')));
});
test('old READY metadata is clearly unconfirmed when cache or server is stale',()=>{
 for(const change of [{stale:true},{state:'UNKNOWN'}]){
  const value=info();value.monitor.worker.modelLoaded=true;Object.assign(value,change);
  const view=consoleView(value,200);assert.match(view.model,/未确认/);assert.equal(view.phases[0].available,false);
 }
 const value=info();value.monitor.workerStale=true;assert.equal(consoleView(value).phases[1].available,false);
});
test('missing monitor data remains unknown rather than manufacturing progress',()=>{
 const view=consoleView({});assert.equal(view.model,'未确认 / 快照过期');assert.equal(view.phases[0].available,false);assert.equal(view.phases[0].completed,0);
});
test('opening a cached snapshot after a long hidden interval cannot revive old READY',()=>{
 const value=info();value.state='READY';value.monitor.worker.modelLoaded=true;
 const view=consoleView(value,1000);assert.equal(view.title,'状态未知');assert.match(view.model,/未确认/);assert.equal(view.phases[0].available,false);
});
test('renderer builds text nodes, shows phase bars, and never injects HTML',()=>{
 const d=dom(),value=info(Date.now()/1000);value.message='<img src=x onerror=alert(1)>';
 paintGpuConsole(d,value);assert.equal(d.getElementById('gpu-console-message').textContent,value.message);
 assert.equal(d.getElementById('gpu-load-inverse-progress').value,1);assert.equal(d.getElementById('gpu-load-inverse-progress').max,9);
 assert.match(d.getElementById('gpu-load-inverse-count').textContent,/1\/9/);
 assert(d.getElementById('gpu-console-details').children.length>=20);
});
test('card click opens a dedicated large responsive dialog with keyboard-native trigger',()=>{
 for(const id of ['gpu-monitor-open','gpu-console-dialog','gpu-console-close','gpu-console-refresh','gpu-console-details',
  'gpu-load-inverse-progress','gpu-load-forward-progress'])assert(html.includes(`id="${id}"`));
 assert(html.includes('aria-controls="gpu-console-dialog"'));assert(source.includes('showModal()'));
 assert(source.includes("if(!event.target.closest('button,a,input'))openGpuConsole()"));
 assert(css.includes('width:min(1120px'));assert(css.includes('@media(max-width:720px)'));assert(css.includes('prefers-reduced-motion:reduce'));
});
test('console reuses the single status refresh with no additional cloud loop or mutations',()=>{
 const body=source.slice(source.indexOf('async function refreshGpuMonitor'),source.indexOf("$('gpu-monitor-refresh').onclick"));
 assert(body.includes("api('/api/gpu/entry-status',"));assert(body.includes('if(gpuMonitorBusy)return'));
 assert(body.includes('open?5000:15000'));assert(!body.includes("method:'POST'"));
 const open=source.slice(source.indexOf('function openGpuConsole()'),source.indexOf('let pendingGpuHost'));
 assert(!open.includes('entry-start'));assert(!open.includes('confirm-host'));assert(!open.includes('submitGeneration'));
});

test('connection failure is visible rather than normal loading and warns ongoing cost',()=>{const v=consoleView({state:'LOADING',observedAt:Date.now()/1000,diagnostic:{active:true,severity:'error',title:'GPU连接准备失败',detail:'读取主机指纹失败',cost:'GPU可能继续计费',action:'请停止并核实释放'}});assert.equal(v.title,'GPU连接准备失败');assert.match(v.message,/计费/);assert.match(v.message,/停止/);});
