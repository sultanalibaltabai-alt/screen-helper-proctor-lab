import json
import unittest
from answers import format_answers


class AnswerMappingTests(unittest.TestCase):
    def test_full_printed_question_and_options_do_not_discard_a_verified_graph_answer(self):
        graph={'kind':'dijkstra_distance','nodes':['A','B'],'directed':True,
            'edges':[{'from':'A','to':'B','weight':7}],'source':'A','target':'B',
            'options':[{'label':'1) 6','value':'6'},{'label':'2) 7','value':'7'}]}
        value={'answers':[{'question':'P1. Find the shortest path from A to B in the directed graph.',
            'answer':'?','option_labels':['1) 6','2) 7'],'readable':True,'graph':graph},
            {'question':'P2. Which weights allow Dijkstra to work correctly?',
            'answer':'2','option_labels':['1) Negative weights','2) Nonnegative weights'],'readable':True,'graph':None}]}
        self.assertEqual(format_answers(json.dumps(value)),'P1: 2\nP2: 2')

    def test_normalizing_printed_options_cannot_merge_duplicates_or_guess_missing_labels(self):
        for labels in (['2) 7','2) 8'],['6 mm','7 mm'],['A) good','A) bad']):
            value={'answers':[{'question':'Q1','answer':'2','option_labels':labels}]}
            self.assertEqual(format_answers(json.dumps(value)),'API: invalid answer')

    def test_printed_letter_number_and_cyrillic_labels_are_preserved(self):
        for labels,answer,expected in [(['A','B','C','D'],'b)','B'),(['1','2','3','4'],'3)','3'),(['а','б','в','г'],'Б','б'),(['A','B','C','D'],'A; D','A,D')]:
            value=json.dumps({'answers':[{'question':'1','answer':answer,'option_labels':labels}]})
            self.assertEqual(format_answers(value),expected)

    def test_model_cannot_swap_numeric_labels_for_letters_or_return_prose(self):
        for answer in ('B','Answer: 2','2,2','5'):
            value=json.dumps({'answers':[{'question':'1','answer':answer,'option_labels':['1','2','3','4']}]})
            self.assertEqual(format_answers(value),'?')

    def test_three_numeric_questions_keep_their_labels(self):
        text = json.dumps({"answers": [{"question": "A2", "answer": "4"},
            {"question": "A3", "answer": "1"}, {"question": "A4", "answer": "2"}]})
        self.assertEqual(format_answers(text), "A2: 4\nA3: 1\nA4: 2")
        punctuated=json.dumps({'answers':[{'question':'A2.','answer':'4'},
            {'question':'A3)','answer':'1'},{'question':'A4.','answer':'2'}]})
        self.assertEqual(format_answers(punctuated),'A2: 4\nA3: 1\nA4: 2')

    def test_single_and_multiple_selection(self):
        self.assertEqual(format_answers('{"answers":[{"question":"1","answer":"B,D"}]}'), "B,D")
        self.assertEqual(format_answers('{"answers":[{"question":"1","answer":"B)"}]}'), "B")

    def test_cut_off_question_is_not_dropped(self):
        self.assertEqual(format_answers('{"answers":[{"question":"1","answer":"B"},{"question":"2","answer":"?"}]}'), "1: B\n2: ?")

    def test_malformed_empty_duplicate_and_overlong_data_are_not_shown(self):
        for value in ('{"answers": [', '{"answers":[]}', '{"answers":[{"question":"1","answer":""}]}',
            '{"answers":[{"question":"1","answer":"A"},{"question":"1","answer":"B"}]}'):
            self.assertEqual(format_answers(value), "API: invalid answer")


if __name__ == "__main__":
    unittest.main()
