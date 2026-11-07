import unittest,json
from graph_solver import solve,verified_label
from answers import format_answers

def graph(kind='dijkstra_distance',directed=True):
 return {'kind':kind,'nodes':['A','B','C','D','E'],'directed':directed,'source':'A','target':'E','edges':[{'from':a,'to':b,'weight':w} for a,b,w in [('A','B',4),('A','C',1),('C','B',2),('B','D',1),('C','D',5),('D','E',3),('C','E',10)]],'options':[{'label':'2','value':'7'}]}
class GraphTests(unittest.TestCase):
 def test_bellman_ford_negative_edges_and_cycles(self):
  g=graph('bellman_ford_distance');g['edges'][2]['weight']=-2
  self.assertEqual(solve(g),'3')
  g['edges'].append({'from':'B','to':'C','weight':1})
  with self.assertRaises(ValueError):solve(g)
 def test_bfs_distance_and_rejection_of_weighted_or_unreachable_graphs(self):
  g=graph('bfs_distance')
  for edge in g['edges']:edge['weight']=1
  self.assertEqual(solve(g),'2')
  g['edges'][0]['weight']=2
  with self.assertRaises(ValueError):solve(g)
 def test_graph_transcription_is_sufficient_without_model_calculation(self):
  item={'question':'P1','answer':'?','readable':True,'graph':graph(),'option_labels':['1','2','3','4']}
  self.assertEqual(format_answers(json.dumps({'answers':[item]})),'2')
 def test_dijkstra_distance_and_order(self):
  g=graph();self.assertEqual(solve(g),'7');self.assertEqual(verified_label(g),'2');g['kind']='dijkstra_order';self.assertEqual(solve(g),'A,C,B,D,E')
 def test_negative_weights_and_ambiguous_edges_fail_closed(self):
  g=graph();g['edges'][0]['weight']=-1
  with self.assertRaises(ValueError):solve(g)
  g=graph();g['edges'].append(g['edges'][0])
  with self.assertRaises(ValueError):solve(g)
 def test_mst_and_prim(self):
  g=graph('mst_weight',False);g['edges']=[{'from':a,'to':b,'weight':w} for a,b,w in [('A','B',2),('A','C',3),('B','C',1),('B','D',4),('C','D',5),('C','E',6),('D','E',2)]]
  self.assertEqual(solve(g),'9');g['kind']='prim_edges';self.assertEqual(solve(g),'AB,BC,BD,DE')
 def test_kahn_and_cycle(self):
  g=graph('kahn_order');g['edges']=[{'from':a,'to':b,'weight':1} for a,b in [('A','C'),('B','C'),('B','D'),('C','E'),('D','E')]];self.assertEqual(solve(g),'A,B,C,D,E');g['edges'].append({'from':'E','to':'A','weight':1})
  with self.assertRaises(ValueError):solve(g)
 def test_computed_answer_overrides_wrong_model_and_unclear_refuses(self):
  item={'question':'P1','answer':'4','readable':True,'graph':graph()};self.assertEqual(format_answers(json.dumps({'answers':[item]})),'2');item['readable']=False;self.assertEqual(format_answers(json.dumps({'answers':[item]})),'?')
if __name__=='__main__':unittest.main()
