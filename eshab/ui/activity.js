'use strict';
// Activity stays inside its owning window. The desktop island is shelf-only.
const ActivityUI = (() => {
 const tasks = new Map();
 let selected = null, pinned = false, notice = null, opened = false, hideTimer, leaveTimer, recentTimer, structure = '';
 const label = (a,b) => document.documentElement.lang === 'ar' ? a : b;
 const safe = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const panel = () => document.getElementById('activity-panel');
 const slot = () => document.getElementById('activity-slot');
 function active() { return [...tasks.values()].filter(task=>!task.dismissed); }
 function current() {
  const list=active();
  return (pinned?list.find(task=>task.id===selected):null) || list.find(task=>!task.done) || list.find(task=>task.id===selected) || list.at(-1);
 }
 function expand(value) {
  clearTimeout(leaveTimer);opened=value;panel()?.classList.toggle('expanded',value);
  panel()?.querySelector('.activity-summary')?.setAttribute('aria-expanded',String(value));
  panel()?.querySelector('.activity-toggle')?.setAttribute('aria-expanded',String(value));
  const details=panel()?.querySelector('.activity-details');if(details)details.inert=!value;
  if(value)clearTimeout(hideTimer);else scheduleHide();
 }
 function scheduleHide() {
  clearTimeout(hideTimer);
  if(opened||active().some(task=>!task.done))return;
  hideTimer=setTimeout(()=>{notice=null;for(const task of active())task.dismissed=true;render();},7000);
 }
 function render() {
  const box=panel(),holder=slot();if(!box||!holder)return;
  const list=active(),task=current();
  const shown=task||notice;
  holder.hidden=!shown;if(!shown){box.querySelector('.activity-orbit')?.__stopBrand?.();opened=false;clearTimeout(hideTimer);structure='';return;}
  const running=task&&!task.done,failed=task?.failed&&!task?.cancelled;
  const title=notice?.message||task.title;
  const status=task ? (task.cancelled?label('تم طلب الإلغاء','Cancellation requested'):task.status) : label('اسحب · جاهز معك','Eshab · Ready with you');
  const percent=task&&task.progress>=0?Math.round(Math.max(0,Math.min(1,task.progress))*100):null;
  const meterText=running?(percent===null?'…':percent+'%'):(failed?'!':'✓');
  const key=JSON.stringify([task?.id,task?.done,task?.failed,task?.cancelled,task?.outputs,notice,list.map(item=>[item.id,item.done,item.failed])]);
  // Progress updates change text and one bar, preserving pointer/focus targets.
  if(key===structure){
   box.querySelector('.activity-caption b').textContent=title;
   box.querySelector('.activity-caption small').textContent=status;
   box.querySelector('.activity-status').textContent=task?.error||status;
   box.querySelector('.activity-percent').textContent=meterText;
   const meter=box.querySelector('.activity-meter');meter.classList.toggle('indeterminate',!!running&&percent===null);
   meter.querySelector('i').style.width=(percent===null?35:percent)+'%';
   if(percent!==null)meter.setAttribute('aria-valuenow',String(percent));else meter.removeAttribute('aria-valuenow');
   for(const button of box.querySelectorAll('[data-task]')){const item=tasks.get(button.dataset.task);button.querySelector('small').textContent=item.progress>=0?Math.round(item.progress*100)+'%':'…';}
   return;
  }
  structure=key;
  const focused=box.querySelector(':focus')?.dataset.focus;
  box.classList.toggle('running',!!running);box.classList.toggle('failed',!!failed);
  box.querySelector('.activity-orbit')?.__stopBrand?.();
  box.innerHTML=`<div class="activity-summary"><span class="activity-orbit" aria-hidden="true"></span><span class="activity-caption"><b dir="auto">${safe(title)}</b><small dir="auto">${safe(status)}</small></span><span class="activity-percent" dir="ltr">${running?(percent===null?'…':percent+'%'):(failed?'!':'✓')}</span><button class="activity-toggle" data-focus="toggle" aria-expanded="${opened}" aria-label="${label('تفاصيل النشاط','Activity details')}">⌄</button></div>
   <div class="activity-meter ${running&&percent===null?'indeterminate':''}" role="progressbar" ${percent!==null?`aria-valuenow="${percent}" aria-valuemin="0" aria-valuemax="100"`:''} aria-label="${safe(title)}"><i style="width:${percent===null?35:percent}%"></i></div>
   <div class="activity-details" ${opened?'':'inert'}><div class="activity-detail-inner">
    <p class="activity-status" dir="auto">${safe(task?.error||status)}</p>
    ${notice&&task?`<p class="activity-note" dir="auto">${safe(notice.message)}</p>`:''}
    <div class="activity-actions">${running?`<button data-action="cancel" ${task.cancelled?'disabled':''}>${label('إلغاء العملية','Cancel task')}</button>`:''}${task?.outputs?.length?`<button data-action="open">${label('فتح النتيجة','Open result')}</button><button data-action="reveal">${label('موقع الملف','Show in folder')}</button>`:notice?.output?`<button data-action="notice-output">${label('موقع الملف','Show in folder')}</button>`:''}<button data-action="dismiss">${label('إخفاء','Dismiss')}</button></div>
    ${list.length>1?`<div class="activity-history" aria-label="${label('العمليات','Tasks')}">${list.slice(-6).map(item=>`<button data-task="${safe(item.id)}" class="${item.id===task?.id?'active':''}"><span>${item.done?(item.failed?'!':'✓'):'◌'}</span><span dir="auto">${safe(item.title)}</span><small>${item.progress>=0?Math.round(item.progress*100)+'%':'…'}</small></button>`).join('')}</div>`:''}
   </div></div>`;
  box.classList.toggle('expanded',opened);
  startBrand(box.querySelector('.activity-orbit'),27);
  if(focused)box.querySelector(`[data-focus="${focused}"]`)?.focus({preventScroll:true});
 }
 async function act(action) {
  if(action==='notice-output'){await rpc('reveal',{path:notice.output});return;}
  const task=current();
  if(task){await rpc('taskAction',{id:task.id,action});if(action==='dismiss')task.dismissed=true;}
  else notice=null;
  if(action==='dismiss'){selected=null;pinned=false;expand(false);render();}
 }
 function init(values=[]) {
  for(const task of values)tasks.set(task.id,task);
  const box=panel();
  box.addEventListener('pointerenter',()=>expand(true));
  box.addEventListener('pointerleave',()=>{leaveTimer=setTimeout(()=>expand(false),180);});
  box.addEventListener('focusin',()=>expand(true));
  box.addEventListener('focusout',()=>{setTimeout(()=>{if(!box.contains(document.activeElement)&&!box.matches(':hover'))expand(false);},0);});
  box.addEventListener('keydown',event=>{if(event.key==='Escape'){expand(false);box.blur();}});
  box.addEventListener('click',event=>{
   const button=event.target.closest('button');
   if(button?.dataset.task){selected=button.dataset.task;pinned=true;structure='';render();return;}
   if(button?.dataset.action){guarded(()=>act(button.dataset.action))();return;}
   if(event.target.closest('.activity-summary'))expand(!opened);
  });
  render();scheduleHide();
 }
 function update(task) {
  const before=tasks.get(task.id);tasks.set(task.id,task);
  if(!before&&!task.done){notice=null;pinned=false;}
  if(!before||(!before.done&&task.done))selected=task.id;
  // Keep bounded history even during a long editing session.
  if(tasks.size>16)for(const [id,item] of tasks){if(item.done&&id!==selected){tasks.delete(id);if(tasks.size<=12)break;}}
  render();scheduleHide();
 }
 function showNotice(message,output) {
  notice={message:String(message),output};clearTimeout(recentTimer);
  recentTimer=setTimeout(()=>{if(!opened){notice=null;render();}},7000);
  render();scheduleHide();
 }
 return {init,update,notice:showNotice};
})();
