'use strict';
// Matches native BrandMark: stable silhouettes and continuous moving light.
function startBrand(element, size=36) {
 const host=element||document.getElementById('brand-icon');
 host.__stopBrand?.();
 const canvas=document.createElement('canvas');
 canvas.className='brand-mark';canvas.style.width=size+'px';canvas.style.height=size+'px';canvas.setAttribute('role','img');canvas.setAttribute('aria-label','Eshab');
 host.replaceChildren(canvas);
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');
 let hover=0,target=0,previous=performance.now(),frame=0,stopped=false;
 const enter=()=>target=1,leave=()=>target=0;
 host.addEventListener('pointerenter',enter);host.addEventListener('pointerleave',leave);
 host.__stopBrand=()=>{stopped=true;cancelAnimationFrame(frame);host.removeEventListener('pointerenter',enter);host.removeEventListener('pointerleave',leave);};
 function draw(now){
  if(stopped||!canvas.isConnected)return;
  if(now-previous<32){frame=requestAnimationFrame(draw);return;}
  const dt=Math.min(.05,Math.max(0,(now-previous)/1000));previous=now;
  if(document.hidden){frame=requestAnimationFrame(draw);return;}
  hover+=(target-hover)*(1-Math.exp(-10*dt));
  const ratio=Math.min(2,devicePixelRatio||1),side=size;
  if(canvas.width!==Math.round(side*ratio)){canvas.width=Math.round(side*ratio);canvas.height=canvas.width;}
  const ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);ctx.save();ctx.scale(canvas.width/100,canvas.height/100);
  const seconds=reduced.matches?0:Date.now()/1000,phase=seconds*Math.PI*2/8,h=reduced.matches?0:hover;
  const circles=[[50,55,24+.6*Math.sin(phase)],
   [50+1.6*Math.sin(phase),16-2*h+1.2*Math.cos(phase),10.5],
   [16-2*h+1.2*Math.sin(phase+1.1),79+1.5*Math.sin(phase+.8),9],
   [84+2*h+1.2*Math.sin(phase-1.1),79+1.5*Math.sin(phase-.8),9]];
  const fill=ctx.createLinearGradient(26+5*Math.sin(phase),5,82,96);
  fill.addColorStop(0,'rgba(255,255,255,.745)');fill.addColorStop(.42,'rgba(215,230,250,.345)');fill.addColorStop(1,'rgba(130,155,190,.157)');
  const[tx,ty,tr]=circles[1];ctx.beginPath();ctx.moveTo(tx-4,ty+tr*.7);ctx.bezierCurveTo(tx-4,30,44,33,43,38);ctx.lineTo(57,38);ctx.bezierCurveTo(56,33,tx+4,30,tx+4,ty+tr*.7);ctx.closePath();ctx.fillStyle=fill;ctx.fill();
  for(const[x,y]of circles.slice(2)){
   const sign=x<50?-1:1;ctx.beginPath();ctx.moveTo(50+sign*16,69);ctx.bezierCurveTo(50+sign*22,72,x-sign*7,y-6,x-sign*4,y-3);ctx.lineTo(x-sign*7,y+1);ctx.bezierCurveTo(x-sign*9,y-4,50+sign*24,76,50+sign*18,73);ctx.closePath();ctx.fillStyle=fill;ctx.fill();
  }
  for(const[index,[x,y,r]]of circles.entries()){
   ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fillStyle=fill;ctx.fill();
   ctx.strokeStyle='rgba(20,35,55,.333)';ctx.lineWidth=3;ctx.stroke();
   ctx.strokeStyle='rgba(246,252,255,.863)';ctx.lineWidth=1.5;ctx.stroke();
   const angle=-2.85+.65*Math.sin(phase+index*.7);ctx.beginPath();ctx.arc(x,y,r*.82,angle,angle+1.15);
   ctx.strokeStyle='rgba(255,255,255,.686)';ctx.lineWidth=1.6;ctx.lineCap='round';ctx.stroke();
   ctx.beginPath();ctx.arc(x+r*.5*Math.cos(angle+.3),y+r*.5*Math.sin(angle+.3),1.1,0,Math.PI*2);ctx.fillStyle='rgba(255,255,255,.647)';ctx.fill();
  }
  ctx.restore();frame=requestAnimationFrame(draw);
 }
 frame=requestAnimationFrame(draw);
}
