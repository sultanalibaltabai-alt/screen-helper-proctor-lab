import {GRAPHS} from './bank.js';
const NS='http://www.w3.org/2000/svg';
function element(tag,attrs={},text){const e=document.createElementNS(NS,tag);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,String(v));if(text!==undefined)e.textContent=text;return e;}
export function graphFigure(key,id){
 const g=GRAPHS[key];if(!g)return document.createTextNode('');
 const figure=document.createElement('figure');figure.className='graph';
 const svg=element('svg',{viewBox:'0 0 500 200',role:'img','aria-label':'Граф задачи '+id});
 const pos=[[38,95],[170,28],[170,166],[320,65],[460,155]];const coords=Object.fromEntries(g.nodes.map((n,i)=>[n,pos[i]]));
 const markerId='arrow-'+id;
 if(g.directed){const defs=element('defs');const marker=element('marker',{id:markerId,viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:6,markerHeight:6,orient:'auto-start-reverse'});marker.append(element('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'#335b4b'}));defs.append(marker);svg.append(defs);}
 for(const [a,b,w]of g.edges){const [x1,y1]=coords[a],[x2,y2]=coords[b];const d=Math.hypot(x2-x1,y2-y1),ux=(x2-x1)/d,uy=(y2-y1)/d;const attrs={x1:x1+ux*18,y1:y1+uy*18,x2:x2-ux*20,y2:y2-uy*20,stroke:'#638374','stroke-width':2};if(g.directed)attrs['marker-end']='url(#'+markerId+')';svg.append(element('line',attrs));if(key!=='dag')svg.append(element('text',{x:(x1+x2)/2-uy*10,y:(y1+y2)/2+ux*10,fill:'#17251f','text-anchor':'middle','font-size':15,stroke:'white','stroke-width':5,'paint-order':'stroke'},w));}
 for(const n of g.nodes){const [x,y]=coords[n];svg.append(element('circle',{cx:x,cy:y,r:17,fill:'white',stroke:'#244c3c','stroke-width':2}));svg.append(element('text',{x,y:y+5,'text-anchor':'middle','font-size':16,fill:'#17251f'},n));}
 const caption=document.createElement('figcaption');caption.textContent=(g.directed?'Ориентированный':'Неориентированный')+' граф. '+g.edges.map(([a,b,w])=>`${a}${g.directed?'→':'—'}${b}${key==='dag'?'':` (${w})`}`).join('; ');figure.append(svg,caption);return figure;
}
