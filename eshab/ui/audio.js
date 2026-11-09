'use strict';
let audioModel = null;
let audioFrame = false;

function timeLabel(seconds) {
 const value = Math.max(0, Math.round((seconds || 0) * 1000));
 const minutes = Math.floor(value / 60000);
 return `${String(minutes).padStart(2,'0')}:${String(Math.floor(value / 1000) % 60).padStart(2,'0')}.${String(value % 1000).padStart(3,'0')}`;
}
function parseTime(value) {
 const parts = value.trim().split(':');
 if (parts.length > 3 || !parts.every(part => /^\d+(\.\d+)?$/.test(part))) return NaN;
 return parts.reduce((sum, part) => sum * 60 + Number(part), 0);
}
function audioEditor() {
 audioModel = {duration:0, peaks:[], start:0, end:0, position:0, playing:false, dirty:false, ready:false, revision:0};
 $('main').innerHTML = `<section class="audio-editor enter">
  <aside class="audio-tools tool-rail glass"><span class="rail-title">${t('الصوت','AUDIO')}</span>
   <button class="dock-item active" aria-pressed="true">${icon('crop')}<span>${t('قص الوقت','Trim')}</span></button>
   <button class="dock-item" id="audio-normalize">${icon('sliders')}<span>${t('موازنة','Normalize')}</span></button>
   <button class="dock-item" id="audio-channels">${icon('audio')}<span>${t('قنوات','Channels')}</span></button>
   <button class="dock-item" id="audio-bleep">${icon('redact')}<span>${t('صفير','Bleep')}</span></button>
  </aside>
  <section class="audio-workspace">
   <div class="audio-heading"><span class="eyebrow">${t('محرر الصوت','AUDIO STUDIO')}</span><h2>${t('كل لحظة، على ذوقك.','Keep the moments that matter.')}</h2><p class="muted">${t('اسحب طرفي التحديد، أو اكتب الوقت بدقة. اسمع النتيجة ثم احفظ نسخة.','Drag the selection handles or enter an exact time. Preview, then save a copy.')}</p></div>
   <section class="wave-card glass"><div class="wave-heading"><span>${icon('audio')} ${t('موجة الصوت','Waveform')}</span><span id="audio-full-duration" dir="ltr">—</span></div>
    <div class="audio-loading" id="audio-loading"><div class="liquid-orb"></div><span>${t('نجهّز الموجة الصوتية…','Preparing your waveform…')}</span></div>
    <div class="wave-track" id="wave-track" hidden><canvas id="audio-wave"></canvas><div class="wave-selection" id="wave-selection"></div>
     <button class="wave-handle start" id="audio-start-handle" role="slider" aria-label="${t('بداية المقطع','Selection start')}" aria-valuemin="0" aria-valuemax="0" aria-valuenow="0"></button>
     <button class="wave-handle end" id="audio-end-handle" role="slider" aria-label="${t('نهاية المقطع','Selection end')}" aria-valuemin="0" aria-valuemax="0" aria-valuenow="0"></button>
     <div class="audio-playhead" id="audio-playhead"></div>
    </div>
    <div class="wave-ruler" id="wave-ruler" dir="ltr"></div>
    <div class="audio-transport"><button class="round glass primary" id="audio-play" disabled aria-label="${t('تشغيل الجزء المحدد','Play selection')}">▶</button><button class="round glass" id="audio-stop" disabled aria-label="${t('إيقاف','Stop')}">■</button><span class="audio-clock" id="audio-clock" dir="ltr">00:00.000</span><span class="muted transport-hint">${t('معاينة الجزء المحدد','Preview selection')}</span></div>
   </section>
   <section class="audio-range glass"><div><span class="eyebrow">${t('تحديد المقطع','YOUR SELECTION')}</span><h3>${t('البداية والنهاية','Start & end')}</h3></div><div class="time-fields">
     <label>${t('من','From')}<input id="audio-start" type="text" inputmode="decimal" dir="ltr" value="00:00.000" disabled spellcheck="false" aria-label="${t('وقت البداية','Start time')}"></label>
     <span class="range-arrow">→</span><label>${t('إلى','To')}<input id="audio-end" type="text" inputmode="decimal" dir="ltr" value="00:00.000" disabled spellcheck="false" aria-label="${t('وقت النهاية','End time')}"></label>
     <div class="selected-duration"><small>${t('مدة المقطع','Selection length')}</small><strong id="audio-selected-duration" dir="ltr">—</strong></div></div>
     <div class="audio-range-actions">${pill('audio-reset',t('تحديد الكل','Select all'),'undo','small')}${pill('audio-auto',t('إزالة الصمت من الأطراف','Trim edge silence'),'sparkle','small')}<span class="muted">${t('دقة حتى جزء من الثانية','Precision to the millisecond')}</span></div>
   </section>
  </section></section>`;
 $('save').disabled = true;
 on('audio-play','click',async()=>{
  if(audioModel.playing){await rpc('audioStop');return;}
  commitAudioRange();
  await rpc('audioPlay',{start:audioModel.start,end:audioModel.end});
 });
 on('audio-stop','click',()=>rpc('audioStop'));
 on('audio-reset','click',()=>setAudioRange(0,audioModel.duration));
 on('audio-auto','click',()=>{
  if(!audioModel.ready)return;
  const peaks=audioModel.peaks, threshold=Math.max(...peaks)*.035;
  const first=peaks.findIndex(value=>value>threshold),last=peaks.findLastIndex(value=>value>threshold);
  if(first<0||last<first){toast(t('المقطع صامت بالكامل','This clip is silent'));return;}
  setAudioRange(Math.max(0,first/peaks.length*audioModel.duration-.05),Math.min(audioModel.duration,(last+1)/peaks.length*audioModel.duration+.05));
 });
 for(const [id,key] of [['audio-normalize','aud.normalize'],['audio-channels','aud.channels'],['audio-bleep','aud.bleep']])
  on(id,'click',()=>rpc('tool',{files:[state.files[0].path],key}));
 for(const side of ['start','end']){
  const input=$('audio-'+side);
  input.addEventListener('change',guarded(commitAudioRange));
  input.addEventListener('keydown',event=>{if(event.key==='Enter')input.blur();});
  $('audio-'+side+'-handle').addEventListener('keydown',event=>{
   if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
   event.preventDefault();
   const amount=(event.shiftKey?1:.1)*(event.key==='ArrowLeft'?-1:1);
   const value=event.key==='Home'?0:event.key==='End'?audioModel.duration:audioModel[side]+amount;
   setAudioRange(side==='start'?Math.max(0,Math.min(audioModel.end-.05,value)):audioModel.start,
                 side==='end'?Math.min(audioModel.duration,Math.max(audioModel.start+.05,value)):audioModel.end);
  });
 }
 const track=$('wave-track');
 track.addEventListener('pointerdown',event=>{
  if(!audioModel.ready||event.button!==0)return;
  event.preventDefault();track.setPointerCapture(event.pointerId);
  const rect=track.getBoundingClientRect();
  const at=Math.max(0,Math.min(audioModel.duration,(event.clientX-rect.left)/rect.width*audioModel.duration));
  audioModel.drag={side:event.target.id==='audio-start-handle'?'start':event.target.id==='audio-end-handle'?'end':'new',anchor:at,moved:false};
 });
 track.addEventListener('pointermove',event=>{
  const drag=audioModel.drag;if(!drag)return;
  const rect=track.getBoundingClientRect(),value=Math.max(0,Math.min(audioModel.duration,(event.clientX-rect.left)/rect.width*audioModel.duration));
  if(Math.abs(value-drag.anchor)>.005)drag.moved=true;
  if(drag.side==='start')setAudioRange(Math.min(value,audioModel.end-.05),audioModel.end);
  else if(drag.side==='end')setAudioRange(audioModel.start,Math.max(value,audioModel.start+.05));
  else if(Math.abs(value-drag.anchor)>=.05)setAudioRange(Math.min(drag.anchor,value),Math.max(drag.anchor,value));
 });
 track.addEventListener('pointerup',guarded(async()=>{
  const drag=audioModel.drag;audioModel.drag=null;
  if(drag&&!drag.moved&&drag.side==='new'){
   audioModel.position=Math.max(audioModel.start,Math.min(audioModel.end,drag.anchor));
   await rpc('audioSeek',{start:audioModel.start,end:audioModel.end,position:audioModel.position});drawAudio();
  }
 }));
 track.addEventListener('pointercancel',()=>{audioModel.drag=null;});
 new ResizeObserver(drawAudio).observe(track);
 if(state.audio)setAudioData(state.audio);
}
function setAudioData(data) {
 if(!audioModel){if(state)state.audio=data;return;}
 if(!Number.isFinite(data.duration)||data.duration<.05){audioFailure(t('مدة الملف أقصر من الحد المتاح للقص (0.05 ثانية).','This file is shorter than the minimum trim length (0.05 seconds).'));return;}
 Object.assign(audioModel,data,{start:0,end:data.duration,ready:true});
 $('audio-loading').hidden=true;$('wave-track').hidden=false;
 $('audio-full-duration').textContent=timeLabel(data.duration);
 for(const id of ['audio-play','audio-stop','audio-start','audio-end','save'])$(id).disabled=false;
 renderAudioRange();
 $('wave-ruler').innerHTML=[0,.25,.5,.75,1].map(part=>`<span>${timeLabel(data.duration*part)}</span>`).join('');
}
function commitAudioRange(){
 if(!audioModel?.ready)return;
 const start=parseTime($('audio-start').value),end=parseTime($('audio-end').value);
 const valid=Number.isFinite(start)&&Number.isFinite(end)&&start>=0&&end<=audioModel.duration+.001&&end-start>=.05;
 for(const id of ['audio-start','audio-end'])$(id).setAttribute('aria-invalid',String(!valid));
 if(!valid)throw new Error(t('اكتب وقتًا داخل مدة الملف، والنهاية بعد البداية بـ 0.05 ثانية على الأقل.','Enter a time inside the file, with at least 0.05 seconds between start and end.'));
 if(Math.abs(start-audioModel.start)>.0005||Math.abs(end-audioModel.end)>.0005)setAudioRange(start,Math.min(end,audioModel.duration));
}
function setAudioRange(start,end) {
 if(!audioModel.ready)return;
 if(audioModel.playing)rpc('audioStop').catch(()=>{});
 audioModel.start=Math.max(0,start);audioModel.end=Math.min(audioModel.duration,end);
 for(const id of ['audio-start','audio-end'])$(id).removeAttribute('aria-invalid');
 audioModel.dirty=true;audioModel.revision++;renderAudioRange();
}
function renderAudioRange() {
 if(!audioModel?.ready)return;
 const {start,end,duration}=audioModel;
 $('audio-start').value=timeLabel(start);$('audio-end').value=timeLabel(end);
 $('audio-selected-duration').textContent=timeLabel(end-start);
 const selection=$('wave-selection');selection.style.left=start/duration*100+'%';selection.style.width=(end-start)/duration*100+'%';
 for(const side of ['start','end']){
  const handle=$('audio-'+side+'-handle');handle.style.left=audioModel[side]/duration*100+'%';
  handle.setAttribute('aria-valuemax',String(duration));handle.setAttribute('aria-valuenow',String(audioModel[side]));handle.setAttribute('aria-valuetext',timeLabel(audioModel[side]));
 }
 drawAudio();
}
function drawAudio() {
 if(audioFrame||!audioModel?.ready)return;audioFrame=true;
 requestAnimationFrame(()=>{
  audioFrame=false;const canvas=$('audio-wave');if(!canvas)return;
  const rect=canvas.getBoundingClientRect(),ratio=Math.min(2,window.devicePixelRatio||1);
  const {duration,start,end,peaks,position}=audioModel;
  const key=[rect.width,rect.height,ratio,start,end,state.dark,peaks.length].join(':');
  if(audioModel.waveKey!==key){
  audioModel.waveKey=key;canvas.width=Math.round(rect.width*ratio);canvas.height=Math.round(rect.height*ratio);
  const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);
  const bars=Math.max(1,Math.min(peaks.length,Math.floor(rect.width/4))),gap=rect.width/bars;
  for(let i=0;i<bars;i++){
   const peak=peaks[Math.min(peaks.length-1,Math.floor(i/bars*peaks.length))],at=i/bars*duration;
   const height=Math.max(3,peak*(rect.height-36));
   ctx.fillStyle=at>=start&&at<=end?(state.dark?'#a9c9fc':'#5783ca'):(state.dark?'#8f9db04d':'#8697b14d');
   ctx.beginPath();ctx.roundRect(i*gap,(rect.height-height)/2,Math.max(1.5,gap-1.6),height,2);ctx.fill();
  }
  }
  $('audio-playhead').style.left=Math.max(0,Math.min(100,position/duration*100))+'%';
  $('audio-clock').textContent=timeLabel(position);
 });
}
function updateAudioPosition(data) {
 if(!audioModel)return;Object.assign(audioModel,data);
 if($('audio-play')){$('audio-play').textContent=data.playing?'Ⅱ':'▶';$('audio-play').setAttribute('aria-label',data.playing?t('إيقاف مؤقت','Pause'):t('تشغيل الجزء المحدد','Play selection'));}
 drawAudio();
}
function audioFailure(message) {
 if($('audio-loading')&&!audioModel?.ready){
  $('audio-loading').innerHTML=`<span>${esc(message)}</span>${pill('audio-retry',t('إعادة المحاولة','Retry'),'redo','small')}`;
  on('audio-retry','click',async()=>{$('audio-loading').innerHTML=`<div class="liquid-orb"></div><span>${t('نجهّز الموجة الصوتية…','Preparing your waveform…')}</span>`;await rpc('audioReload');});
 }
 if(audioModel)audioModel.playing=false;
 updateAudioPosition({playing:false});toast(message);
}
async function saveAudio() {
 if(saving||!audioModel?.ready)return;
 commitAudioRange();
 saving=true;$('save').disabled=true;$('save').querySelector('span').textContent=t('جارٍ الحفظ…','Saving…');
 const revision=audioModel.revision;
 const saved=new Promise((resolve,reject)=>{saveResolve=resolve;saveReject=reject;});
 try{
  await rpc('saveAudio',{start:audioModel.start,end:audioModel.end});
  lastSaved=await saved;if(audioModel.revision===revision)audioModel.dirty=false;return lastSaved;
 }finally{
  saving=false;saveResolve=saveReject=null;$('save').disabled=false;$('save').querySelector('span').textContent=t('حفظ نسخة','Save a copy');
 }
}
