import json
import unittest
from answers import format_answers,ANSWER_SCHEMA,is_control_answer

def solution(kind,**fields):
    return dict({'kind':kind,'selected_labels':[],'options':[],'text':'','pairs':[],'sequence':[],'explanation':''},**fields)

def entry(kind,answer='result',**fields):
    value=solution(kind);value.update(fields)
    return {'question':'Q1','answer':answer,'option_labels':[],'readable':True,'graph':None,'solution':value}

class FullAnswerTests(unittest.TestCase):
    def show(self,item):return format_answers(json.dumps({'answers':[item]},ensure_ascii=False))
    def test_single_choice_returns_the_full_printed_answer(self):
        item=entry('single_choice','B',selected_labels=['B'],options=[{'label':'A','text':'60 мм'},{'label':'B','text':'61 мм'}]);item['option_labels']=['A','B']
        self.assertEqual(self.show(item),'B) 61 мм')
    def test_msq_returns_every_selected_option_with_its_text(self):
        item=entry('multiple_choice','1,3',selected_labels=['3','1'],options=[{'label':'1','text':'Крускал'},{'label':'2','text':'Дейкстра'},{'label':'3','text':'Прим'}]);item['option_labels']=['1','2','3']
        self.assertEqual(self.show(item),'1) Крускал\n3) Прим')
        item['solution']['selected_labels']=['2'];self.assertEqual(self.show(item),'?')
    def test_matching_and_drag_drop_preserve_explicit_source_target_pairs(self):
        for kind in ('matching','drag_drop','fill_blanks'):
            item=entry(kind,pairs=[{'from':'A','to':'Категория 1'},{'from':'B','to':'Категория 1'}])
            self.assertEqual(self.show(item),'A → Категория 1\nB → Категория 1')
            item['solution']['pairs'].append({'from':'A','to':'Категория 2'});self.assertEqual(self.show(item),'?')
    def test_unlabeled_checkbox_quiz_uses_full_text_without_inventing_letters(self):
        item=entry('multiple_choice','two selected',options=[{'label':'','text':'Первый пункт','selected':True},{'label':'','text':'Второй пункт','selected':False},{'label':'','text':'Третий пункт','selected':True}])
        self.assertEqual(self.show(item),'• Первый пункт\n• Третий пункт')
        item['solution']['kind']='single_choice';self.assertEqual(self.show(item),'?')
    def test_ordering_returns_the_complete_sequence(self):
        self.assertEqual(self.show(entry('ordering',sequence=['Инициализация','Сортировка рёбер','Объединение компонент'])),'1. Инициализация\n2. Сортировка рёбер\n3. Объединение компонент')
    def test_free_text_code_numeric_and_true_false_are_not_truncated_to_a_letter(self):
        for kind,text in [('text','Полный ответ.\n'+('Пример. '*100)),('code','def f(x):\n    return x + 1'),('numeric','61 мм'),('true_false','Верно')]:
            self.assertEqual(self.show(entry(kind,text=text)),text.strip())
    def test_graph_verification_overrides_a_wrong_model_selection_and_explanation(self):
        item=entry('single_choice','1',selected_labels=['1'],options=[{'label':'1','text':'6'},{'label':'2','text':'7'}],explanation='incorrect model claim')
        item['option_labels']=['1','2'];item['graph']={'kind':'dijkstra_distance','nodes':['A','B'],'directed':True,'edges':[{'from':'A','to':'B','weight':7}],'source':'A','target':'B','options':[{'label':'1','value':'6'},{'label':'2','value':'7'}]}
        self.assertEqual(self.show(item),'2) 7')
        item['graph']['options']=[];item['option_labels']=[];item['solution']=solution('numeric',text='wrong')
        self.assertEqual(self.show(item),'7')
    def test_unreadable_missing_options_and_empty_interactions_remain_uncertain(self):
        item=entry('text',text='invented');item['readable']=False;self.assertEqual(self.show(item),'?')
        self.assertEqual(self.show(entry('matching')),'?')
        item=entry('single_choice','B',selected_labels=['B'],options=[]);item['option_labels']=['A','B'];self.assertEqual(self.show(item),'?')
    def test_rich_multi_question_output_keeps_separate_identifiers(self):
        one=entry('text',text='Первый ответ');two=entry('numeric',text='42');two['question']='Q2'
        self.assertEqual(format_answers(json.dumps({'answers':[one,two]},ensure_ascii=False)),'Q1: Первый ответ\n\nQ2: 42')
    def test_schema_remains_strict_for_every_nested_object(self):
        def walk(value):
            if isinstance(value,dict):
                if 'properties' in value:
                    self.assertFalse(value['additionalProperties']);self.assertEqual(set(value['properties']),set(value['required']))
                for child in value.values():walk(child)
            elif isinstance(value,list):
                for child in value:walk(child)
        walk(ANSWER_SCHEMA)
    def test_control_question_accepts_a_full_answer_and_rejects_wrong_option_content(self):
        for value in ('B','B) 4'):self.assertTrue(is_control_answer(value))
        for value in ('B) 3','A) 4','B,D','?'):self.assertFalse(is_control_answer(value))
    def test_valid_api_definition_is_not_mistaken_for_an_application_error(self):
        self.assertEqual(self.show(entry('text',text='API: программный интерфейс')),'Ответ:\nAPI: программный интерфейс')
    def test_openai_extraction_keeps_code_indentation_and_newlines(self):
        import helper
        code='def f(x):\n    if x:\n        return x + 1'
        raw=json.dumps({'answers':[entry('code',text=code)]})
        self.assertEqual(helper.extract_answer({'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':raw}]}]}),code)

if __name__=='__main__':unittest.main()
