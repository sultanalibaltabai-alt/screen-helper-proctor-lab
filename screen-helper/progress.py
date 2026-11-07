"""Local process stages and elapsed time, without invented model percentages."""
import json
import time

STAGES={'capture':'Захват окна','encoding':'Подготовка снимка','request':'Отправка / ожидание API',
        'retry':'Повтор после ошибки API','receiving':'Получение данных','validating':'Проверка ответа',
        'fallback':'Резервная модель','cached':'Готовый результат из кэша','cancelling':'Отмена запроса',
        'cancelled':'Запрос отменён','done':'Завершено','stopped':'Процесс остановлен локально'}

class RequestProgress:
    def __init__(self, token, clock=time.monotonic):
        self.clock=clock;self.token=token;self.started=clock();self.phase='capture';self.changed=self.started;self.ended=None
    def update(self,phase):
        if phase not in STAGES:raise ValueError('Unknown process stage')
        if self.ended is not None:return
        if phase!=self.phase:self.phase=phase;self.changed=self.clock()
        if phase in ('done','stopped','cancelled'):self.ended=self.clock()
    def snapshot(self):
        now=self.ended if self.ended is not None else self.clock()
        return {'request_id':self.token,'state':'working' if self.ended is None else self.phase,
                'stage':self.phase,'label':STAGES[self.phase],
                'elapsed_seconds':round(max(0,now-self.started),1),'stage_seconds':round(max(0,now-self.changed),1)}
    def text(self):
        value=self.snapshot()
        return f"{value['label']} · {int(value['elapsed_seconds'])} с"

def save_status(path,value):
    temporary=path.with_suffix('.tmp')
    try:
        temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(path)
    except OSError:pass
