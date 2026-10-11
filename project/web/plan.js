// Isolated recommendation state. No generation adapter or file access.
export function createPlan(ids = []) {
  return { ids: [...ids], excluded: [], reasons: [], unsupported: [], question: '', previous: null,
    revision: 0, request: null, busy: false, error: '', source: 'manual', replyStatus:null };
}
export function changePlan(plan, ids, extra = {}) {
  return { ...plan, ids: [...ids], reasons: [], unsupported: [], question: '', excluded: plan.excluded.filter(id=>!ids.includes(id)), replyStatus:null, ...extra,
    previous: { ids: plan.ids, reasons: plan.reasons, excluded: plan.excluded, unsupported: plan.unsupported, question: plan.question, source: plan.source, replyStatus:plan.replyStatus },
    revision: plan.revision + 1, busy: false, request: null, error: '' };
}
export function undoPlan(plan) {
  return plan.previous ? { ...plan, ...plan.previous, previous: null, revision: plan.revision + 1, request: null, busy: false, error: '' } : plan;
}
export function invalidatePlan(plan) {
  return { ...plan, revision: plan.revision + 1, request: null, busy: false, error: '', question: '', replyStatus:null };
}
export function beginRecommendation(plan, token) {
  return plan.busy ? plan : { ...plan, request: token, busy: true, error: '' };
}
export function applyRecommendation(plan, token, value, allowed) {
  if (plan.request !== token) return plan;
  const keys = ['status','presetIds','reasons','excludedIds','unsupported','question'];
  const ids = (items, enumIds, max=3) => Array.isArray(items) && items.length <= max && items.every(i=>typeof i==='string' && enumIds.includes(i)) && new Set(items).size===items.length;
  const valid = value && Object.keys(value).length===keys.length && keys.every(k=>Object.hasOwn(value,k)) &&
    ['ready','clarification','unsupported'].includes(value.status) && ids(value.presetIds,allowed) && ids(value.excludedIds,allowed) &&
    !value.presetIds.some(i=>value.excludedIds.includes(i)) && ids(value.unsupported,['precision','material_detail','unrelated']) &&
    Array.isArray(value.reasons) && value.reasons.length===value.presetIds.length && value.reasons.every(r=>typeof r==='string' && r.trim().length>0 && r.length<=60) &&
    typeof value.question==='string' && value.question.length<=100 &&
    (value.status==='ready' ? value.presetIds.length>0 && !value.question : value.presetIds.length===0 && (value.status==='clarification' ? !!value.question.trim() : value.unsupported.length>0 && !value.question));
  if (!valid) return failRecommendation(plan, token, '文字服务返回无效，方案未修改。');
  if (value.status !== 'ready') return { ...plan, busy: false, request: null, unsupported: value.unsupported, question: value.question, error: '', replyStatus:value.status };
  return changePlan(plan, value.presetIds, { reasons: value.reasons, excluded: value.excludedIds, unsupported: value.unsupported, source: 'language', replyStatus:'ready' });
}
export function failRecommendation(plan, token, error) {
  return plan.request === token ? { ...plan, busy: false, request: null, error } : plan;
}
export function validResult(state, id, now = Date.now()) {
  const tasks = [...new Set([state.task, ...Object.values(state.tasks || {})])].filter(Boolean);
  for (const task of tasks) {
    if (task.input?.id !== state.upload?.id || !task.expiresAt || task.expiresAt*1000 <= now || ['failed','expired'].includes(task.status)) continue;
    const item = task.presetResults?.[id] || (task.preset?.id===id ? task : null);
    const result = item?.result;
    if (item?.status==='succeeded' && result?.taskId===task.taskId && result.inputId===state.upload?.id && result.presetId===id) return task;
  }
  return null;
}
export function missingPresets(state, ids) { return ids.filter(id=>!validResult(state,id)); }
