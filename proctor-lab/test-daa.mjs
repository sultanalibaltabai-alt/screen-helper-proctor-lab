import test from 'node:test';
import assert from 'node:assert/strict';
import {WORKS,GRAPHS,pickQuestions} from './dist/bank.js';
import {Session} from './dist/core.js';
test('DAA bank has 18 unique, valid questions and two disjoint variants per work',()=>{
 const ids=new Set();for(const name of ['mst','paths','dag']){assert.equal(WORKS[name].questions.length,6);for(const q of WORKS[name].questions){assert(!ids.has(q.id));ids.add(q.id);assert.equal(q.options.length,4);assert.match(q.correct,/^[1-4]$/);assert(q.explanation);}
 assert.equal(new Set([...pickQuestions(name,3,0),...pickQuestions(name,3,3)].map(q=>q.id)).size,6);}
});
test('independent Kruskal calculation verifies MST answer',()=>{const parent=Object.fromEntries(GRAPHS.mst.nodes.map(n=>[n,n]));const find=x=>parent[x]===x?x:parent[x]=find(parent[x]);let sum=0;for(const [a,b,w]of [...GRAPHS.mst.edges].sort((x,y)=>x[2]-y[2])){const x=find(a),y=find(b);if(x!==y){parent[x]=y;sum+=w;}}assert.equal(sum,9);assert.equal(WORKS.mst.questions[0].options[Number(WORKS.mst.questions[0].correct)-1],String(sum));});
test('independent repeated relaxation verifies shortest path distances',()=>{const g=GRAPHS.shortest,d=Object.fromEntries(g.nodes.map(n=>[n,n==='A'?0:Infinity]));for(let pass=0;pass<g.nodes.length-1;pass++)for(const [a,b,w]of g.edges)d[b]=Math.min(d[b],d[a]+w);assert.deepEqual(d,{A:0,B:3,C:1,D:4,E:7});});
test('independent Kahn calculation verifies deterministic order',()=>{const g=GRAPHS.dag,ind=Object.fromEntries(g.nodes.map(n=>[n,0]));for(const [,b]of g.edges)ind[b]++;const result=[];while(result.length<g.nodes.length){const n=g.nodes.filter(n=>ind[n]===0&&!result.includes(n)).sort()[0];assert(n);result.push(n);for(const [a,b]of g.edges)if(a===n)ind[b]--;}assert.deepEqual(result,['A','B','C','D','E']);});
test('strict warning blocks choices, timer continues, resume and finish stay available',()=>{let now=1000;const s=new Session(()=>now);s.start({strict:true,work:'mst',duration:60});s.record('blur');assert.equal(s.paused,'blur');assert.equal(s.choose('M1','2'),false);now+=5000;assert.equal(s.remaining(),55);assert(s.resume());assert(s.choose('M1','2'));s.record('extension_new_tab');assert(s.paused);assert.equal(s.finish().score,1);assert.equal(s.resume(),false);});
