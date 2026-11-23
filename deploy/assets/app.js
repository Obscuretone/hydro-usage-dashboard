'use strict';
const HOUR=3600000,DAY=24*HOUR;
const byId=id=>document.getElementById(id);
const format=(n,d=1)=>Number.isFinite(n)?n.toLocaleString('en-CA',{maximumFractionDigits:d,minimumFractionDigits:d}):'—';
const wallTime=r=>Date.parse(r.day+'T'+String(r.hour).padStart(2,'0')+':00:00Z');
// Axis values deliberately represent Toronto wall-clock labels. Plotly does not
// apply the visitor's timezone, and hourly energy is never interpolated.
function series(data){
 const hours=[...data.hours].sort((a,b)=>wallTime(a)-wallTime(b));
 if(!hours.length)throw Error('No readings are available yet.');
 const start=wallTime(hours[0]),end=wallTime(hours[hours.length-1])+HOUR;
 const energy=new Map(hours.map(r=>[wallTime(r),r]));
 const daily=new Map(data.daily.map(r=>[r.dateJourConso,r.tempMoyenneQuot]));
 const x=[],usage=[],temperature=[],dayLabels=[];
 for(let t=start;t<end;t+=HOUR){const day=new Date(t).toISOString().slice(0,10),r=energy.get(t),temp=daily.get(day);x.push(new Date(t).toISOString().slice(0,19));usage.push(r?r.kwh:null);temperature.push(Number.isFinite(temp)?temp:null);dayLabels.push(day)}
 return {hours,start,end,x,usage,temperature,dayLabels};
}
function visibleStats(hours,range){const selected=hours.filter(r=>wallTime(r)>=range[0]&&wallTime(r)<range[1]);const total=selected.reduce((n,r)=>n+r.kwh,0);return {count:selected.length,total,average:selected.length?total/selected.length:NaN,peak:selected.length?Math.max(...selected.map(r=>r.kwh)):NaN}}
function clampRange(a,b,start,end){let width=Math.min(b-a,end-start);if(!Number.isFinite(width)||width<=0)width=Math.min(7*DAY,end-start);let left=Math.max(start,Math.min(a,end-width));return[left,left+width]}
function freshness(data,now=Date.now()){
 const refresh=data.refresh||{},lastSuccess=refresh.last_success_at||data.synced;
 const success=Date.parse(lastSuccess),latest=data.hours[data.hours.length-1],latestTime=Date.parse(latest.time);
 const stamp=Number.isFinite(success)?new Date(success).toLocaleString('en-CA',{timeZone:'America/Toronto',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}):'not recorded';
 let warning='';
 if(refresh.state==='sign_in_required')warning='Hydro sign-in required. Showing saved readings.';
 else if(refresh.state==='sync_failed')warning='The last refresh failed. Showing saved readings.';
 else if(!Number.isFinite(success)||now-success>3*HOUR)warning='Updates are overdue. Showing saved readings.';
 else if(!Number.isFinite(latestTime)||now-latestTime>3*DAY)warning='Hydro has not supplied recent readings. Showing the latest available data.';
 return {text:(data.hours.every(r=>r.quality==='synthetic')?'Synthetic demo · ':'')+'Readings through '+latest.day+' '+String(latest.hour).padStart(2,'0')+':00 · last successful sync '+stamp,warning};
}
let DATA,SERIES,RANGE,ready=false;
function dateLabel(t){return new Date(t).toLocaleDateString('en-CA',{timeZone:'UTC',month:'short',day:'numeric'})}
function updateStats(){const s=visibleStats(SERIES.hours,RANGE);byId('total').textContent=format(s.total)+' kWh';byId('average').textContent=format(s.average,2)+' kWh';byId('peak').textContent=format(s.peak,2)+' kWh';byId('period').textContent=dateLabel(RANGE[0])+' – '+dateLabel(RANGE[1]-1)+' · '+s.count.toLocaleString()+' available hours';document.querySelectorAll('[data-days]').forEach(button=>{const days=button.dataset.days,active=days==='all'?RANGE[0]===SERIES.start&&RANGE[1]===SERIES.end:Math.abs((RANGE[1]-RANGE[0])/DAY-Number(days))<.02;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active))})}
function showRange(a,b){RANGE=clampRange(a,b,SERIES.start,SERIES.end);Plotly.relayout('graph',{'xaxis.range':[new Date(RANGE[0]).toISOString().slice(0,19),new Date(RANGE[1]).toISOString().slice(0,19)]});updateStats()}
function step(direction){if(ready){const amount=(RANGE[1]-RANGE[0])*.8*direction;showRange(RANGE[0]+amount,RANGE[1]+amount)}}
async function load(){try{
 const res=await fetch('data.json',{cache:'no-store'});if(res.status===401)throw Error('Your dashboard sign-in expired. Reload this page to sign in again.');if(!res.ok)throw Error('Unable to load readings ('+res.status+').');DATA=await res.json();SERIES=series(DATA);RANGE=ready&&RANGE?clampRange(...RANGE,SERIES.start,SERIES.end):[Math.max(SERIES.start,SERIES.end-7*DAY),SERIES.end];
 const current=freshness(DATA);byId('freshness').textContent=current.text;byId('error').textContent=current.warning;
 const narrow=window.innerWidth<650;
 await Plotly.react('graph',[
  {x:SERIES.x,y:SERIES.usage,type:'bar',name:'Hourly usage',marker:{color:'#63d9bd'},opacity:.86,hovertemplate:'%{x|%b %d, %H:%M}<br><b>%{y:.2f} kWh</b> used during this hour<extra></extra>'},
  {x:SERIES.x,y:SERIES.temperature,type:'scatter',mode:'lines',name:'Outside · daily mean',yaxis:'y2',connectgaps:false,line:{color:'#ecb16a',width:2,shape:'hv'},customdata:SERIES.dayLabels,hovertemplate:'%{customdata}<br>Outside daily mean: <b>%{y:.1f}°C</b><extra></extra>'}
 ],{
  paper_bgcolor:'#102126',plot_bgcolor:'#102126',font:{family:'system-ui',color:'#92aaa9',size:narrow?10:12},margin:{l:narrow?42:58,r:narrow?42:58,t:22,b:30},showlegend:false,dragmode:'pan',hovermode:'x unified',hoverlabel:{bgcolor:'#183139',bordercolor:'#36555a',font:{color:'#e7f0ef'}},bargap:.12,uirevision:'hydro-simple',
  xaxis:{type:'date',range:RANGE.map(t=>new Date(t).toISOString().slice(0,19)),gridcolor:'#20363c',zeroline:false,tickformat:'%b %d\n%H:%M',rangeslider:{visible:true,thickness:.12,bgcolor:'#0c191e',borderwidth:0,range:[new Date(SERIES.start).toISOString().slice(0,19),new Date(SERIES.end).toISOString().slice(0,19)]}},
  yaxis:{title:{text:'kWh',font:{color:'#63d9bd',size:12}},rangemode:'tozero',fixedrange:true,gridcolor:'#23383e',zerolinecolor:'#365057'},
  yaxis2:{title:{text:'°C',font:{color:'#ecb16a',size:12}},overlaying:'y',side:'right',showgrid:false,zeroline:false,fixedrange:true,tickfont:{color:'#ecb16a'}}
 },{responsive:true,displayModeBar:false,scrollZoom:false,doubleClick:'reset'});
 if(!ready){const graph=byId('graph');graph.on('plotly_relayout',event=>{if(event['xaxis.autorange']){RANGE=[SERIES.start,SERIES.end];updateStats();return}const r=event['xaxis.range']||[event['xaxis.range[0]'],event['xaxis.range[1]']];if(r[0]&&r[1]){const parse=t=>typeof t==='number'?t:Date.parse(String(t).replace(' ','T').replace(/Z$/,'')+'Z');RANGE=clampRange(parse(r[0]),parse(r[1]),SERIES.start,SERIES.end);updateStats()}});
 graph.addEventListener('wheel',event=>{if(!event.shiftKey&&Math.abs(event.deltaX)<=Math.abs(event.deltaY))return;event.preventDefault();const delta=(event.deltaX||event.deltaY)/graph.clientWidth*(RANGE[1]-RANGE[0]);showRange(RANGE[0]+delta,RANGE[1]+delta)},{passive:false});graph.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();step(e.key==='ArrowLeft'?-1:1)}});
 }
 ready=true;updateStats();
 }catch(e){byId('error').textContent=e.message}}
if(typeof document!=='undefined'){
 document.querySelectorAll('[data-days]').forEach(b=>b.onclick=()=>{if(!ready)return;const n=b.dataset.days;showRange(n==='all'?SERIES.start:SERIES.end-Number(n)*DAY,SERIES.end)});
 byId('earlier').onclick=()=>step(-1);byId('later').onclick=()=>step(1);byId('refresh').onclick=load;load();
}
if(typeof module!=='undefined')module.exports={series,visibleStats,clampRange,wallTime,freshness};
