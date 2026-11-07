"""Deterministic graph algorithms over explicitly validated OCR data."""
import heapq
import math
from collections import deque


def solve(graph):
    nodes = graph['nodes']
    if not isinstance(nodes,list) or not 1 <= len(nodes) <= 100 or any(not isinstance(n,str) or not n or len(n)>24 for n in nodes) or len(set(nodes))!=len(nodes):
        raise ValueError('invalid vertices')
    if not isinstance(graph['directed'],bool) or len(graph['edges'])>1000:
        raise ValueError('invalid graph')
    adjacency={n:[] for n in nodes}; edges=[]; seen=set()
    for edge in graph['edges']:
        a,b,w=edge['from'],edge['to'],edge['weight']
        if a not in adjacency or b not in adjacency or isinstance(w,bool) or not isinstance(w,(float,int)) or not math.isfinite(w):
            raise ValueError('invalid edge')
        identity=(a,b) if graph['directed'] else tuple(sorted((a,b)))
        if identity in seen:raise ValueError('ambiguous parallel edges')
        seen.add(identity);edges.append((a,b,w));adjacency[a].append((b,w))
        if not graph['directed']:adjacency[b].append((a,w))
    kind=graph['kind'];source=graph['source'];target=graph['target']
    if kind in ('bellman_ford_distance','bfs_distance'):
        if source not in adjacency or target not in adjacency:raise ValueError('invalid source or target')
        distances={n:math.inf for n in nodes};distances[source]=0
        if kind=='bfs_distance':
            if any(w!=1 for a,b,w in edges):raise ValueError('BFS requires unweighted edges')
            queue=deque([source])
            while queue:
                a=queue.popleft()
                for b,w in adjacency[a]:
                    if not math.isfinite(distances[b]):distances[b]=distances[a]+1;queue.append(b)
        else:
            for _ in range(len(nodes)-1):
                changed=False
                for a in nodes:
                    for b,w in adjacency[a]:
                        if distances[a]+w<distances[b]:distances[b]=distances[a]+w;changed=True
                if not changed:break
            if any(distances[a]+w<distances[b] for a in nodes for b,w in adjacency[a]):raise ValueError('reachable negative cycle')
        value=distances[target]
        if not math.isfinite(value):raise ValueError('unreachable target')
        return str(int(value)) if float(value).is_integer() else str(value)
    if kind=='mst_weight':
        if graph['directed']:raise ValueError('MST requires undirected graph')
        parent={n:n for n in nodes}
        def find(n):
            while parent[n]!=n:parent[n]=parent[parent[n]];n=parent[n]
            return n
        total=0;count=0
        for a,b,w in sorted(edges,key=lambda e:(e[2],min(e[0],e[1]),max(e[0],e[1]))):
            x,y=find(a),find(b)
            if x!=y:parent[x]=y;total+=w;count+=1
        if count!=len(nodes)-1:raise ValueError('disconnected graph')
        return str(int(total)) if float(total).is_integer() else str(total)
    if kind=='prim_edges':
        if graph['directed'] or source not in adjacency:raise ValueError('invalid Prim graph')
        used={source};result=[]
        while len(used)<len(nodes):
            candidates=[(w,min(a,b),max(a,b),b) for a in used for b,w in adjacency[a] if b not in used]
            if not candidates:raise ValueError('disconnected graph')
            w,a,b,new=min(candidates);used.add(new);result.append(a+b)
        return ','.join(result)
    if kind in ('dijkstra_distance','dijkstra_order'):
        if source not in adjacency or any(w<0 for a,b,w in edges):raise ValueError('Dijkstra requires nonnegative weights')
        distances={n:math.inf for n in nodes};distances[source]=0;heap=[(0,source)];used=set();order=[]
        while heap:
            d,a=heapq.heappop(heap)
            if a in used:continue
            used.add(a);order.append(a)
            for b,w in adjacency[a]:
                if d+w<distances[b]:distances[b]=d+w;heapq.heappush(heap,(d+w,b))
        if kind=='dijkstra_order':return ','.join(order)
        if target not in distances or not math.isfinite(distances[target]):raise ValueError('unreachable target')
        value=distances[target];return str(int(value)) if float(value).is_integer() else str(value)
    if kind=='kahn_order':
        if not graph['directed']:raise ValueError('Kahn requires directed graph')
        degree={n:0 for n in nodes}
        for a,b,w in edges:degree[b]+=1
        heap=[n for n in nodes if degree[n]==0];heapq.heapify(heap);order=[]
        while heap:
            a=heapq.heappop(heap);order.append(a)
            for b,w in adjacency[a]:
                degree[b]-=1
                if degree[b]==0:heapq.heappush(heap,b)
        if len(order)!=len(nodes):raise ValueError('cycle')
        return ','.join(order)
    raise ValueError('unsupported algorithm')


def verified_label(graph):
    value=solve(graph)
    normalize=lambda s:''.join(str(s).split()).replace('→',',').replace('−','-')
    matches=[item['label'] for item in graph['options'] if normalize(item['value'])==normalize(value)]
    return matches[0] if len(matches)==1 else '?'
