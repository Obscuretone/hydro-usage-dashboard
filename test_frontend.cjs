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
