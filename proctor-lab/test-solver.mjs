import test from 'node:test';import assert from 'node:assert/strict';
import {solveGraph,checkedAnswer} from './dist/solve-graph.js';
import {GRAPHS} from './dist/bank.js';
const sample=(key,kind)=>({kind,nodes:GRAPHS[key].nodes,directed:GRAPHS[key].directed,edges:GRAPHS[key].edges.map(([a,b,w])=>({from:a,to:b,weight:w})),source:'A',target:'E',options:[{label:'2',value:'7'}]});
test('browser graph engine agrees on MST, Prim, Dijkstra and Kahn',()=>{assert.equal(solveGraph(sample('mst','mst_weight')),'9');assert.equal(solveGraph(sample('mst','prim_edges')),'AB,BC,BD,DE');assert.equal(solveGraph(sample('shortest','dijkstra_distance')),'7');assert.equal(solveGraph(sample('shortest','dijkstra_order')),'A,C,B,D,E');assert.equal(solveGraph(sample('dag','kahn_order')),'A,B,C,D,E');});
test('unclear input refuses; computed result overrides wrong model',()=>{const item={answer:'4',readable:true,graph:sample('shortest','dijkstra_distance')};assert.equal(checkedAnswer(item).answer,'2');item.readable=false;assert.equal(checkedAnswer(item).answer,'?');});
test('negative Dijkstra and graph cycles do not produce answer labels',()=>{const g=sample('shortest','dijkstra_distance');g.edges[0].weight=-1;assert.equal(checkedAnswer({readable:true,graph:g}).answer,'?');const d=sample('dag','kahn_order');d.edges.push({from:'E',to:'A',weight:1});assert.throws(()=>solveGraph(d));});
