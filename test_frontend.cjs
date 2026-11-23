'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {series,visibleStats,clampRange}=require('./deploy/assets/app.js');
const hours=[{day:'2026-10-01',hour:0,kwh:1},{day:'2026-10-01',hour:2,kwh:3},{day:'2026-10-02',hour:0,kwh:2}];
test('missing usage stays empty, zero temperature is valid, missing temperature stays empty',()=>{
 const s=series({hours,daily:[{dateJourConso:'2026-10-01',tempMoyenneQuot:0}]});
 assert.deepEqual(s.usage.slice(0,3),[1,null,3]);
 assert.equal(s.temperature[0],0);assert.equal(s.temperature[24],null);
});
test('visible totals exclude missing readings and use half-open bounds',()=>{
 const s=series({hours,daily:[]});
 assert.deepEqual(visibleStats(hours,[s.start,s.start+2*3600000]),{count:1,total:1,average:1,peak:1});
 assert.ok(Number.isNaN(visibleStats(hours,[s.start+3600000,s.start+2*3600000]).average));
});
test('panning stays inside available data',()=>{
 assert.deepEqual(clampRange(-10,10,0,100),[0,20]);
 assert.deepEqual(clampRange(90,110,0,100),[80,100]);
 assert.deepEqual(clampRange(-100,200,0,100),[0,100]);
});
const {freshness}=require('./deploy/assets/app.js');
const now=Date.parse('2026-11-23T18:00:00Z');
const fresh={synced:'2026-11-23T17:30:00Z',hours:[{day:'2026-11-22',hour:23,time:'2026-11-22T23:00:00-05:00',kwh:1}]};
test('fresh readings show the actual successful sync time',()=>{
 const f=freshness(fresh,now);assert.equal(f.warning,'');assert.match(f.text,/last successful sync/);assert.doesNotMatch(f.text,/checked hourly/);
});
test('newly generated snapshots cannot conceal an old sync',()=>{
 assert.match(freshness({...fresh,synced:'2026-11-13T01:00:00Z',generated:'2026-11-23T18:00:00Z'},now).warning,/overdue/);
});
test('authentication failure stays visible with saved readings',()=>{
 assert.match(freshness({...fresh,refresh:{state:'sign_in_required',last_success_at:fresh.synced}},now).warning,/sign-in required/);
 assert.match(freshness({...fresh,refresh:{state:'sync_failed'}},now).warning,/refresh failed/);
});

test('weather estimates use Toronto time and retain zero and gaps',()=>{
 const {weatherWall,weatherSummary}=require('./deploy/assets/app.js');
 assert.equal(weatherWall('2026-11-24T00:00:00Z'),Date.parse('2026-11-23T19:00:00Z'));
 const w={label:'Example',state:'ok',current:{time:'2026-11-23T23:30:00Z',temp:0}};
 assert.match(weatherSummary(w,Date.parse('2026-11-23T23:45:00Z')),/0.0°C/);
 assert.match(weatherSummary(w,Date.parse('2026-11-24T04:00:00Z')),/overdue/);
 w.state='fetch_failed';assert.match(weatherSummary(w,Date.parse('2026-11-23T23:45:00Z')),/overdue/);
});
