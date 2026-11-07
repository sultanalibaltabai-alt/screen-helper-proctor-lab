// Page integrity signals; this module cannot inspect OS processes or isolated worlds.
export function executableScript(node){
  return node?.nodeType===1&&node.tagName==='SCRIPT'&&['','module','text/javascript','application/javascript','text/ecmascript','application/ecmascript','application/x-javascript'].includes((node.getAttribute('type')||'').trim().toLowerCase().split(';')[0]);
}
export class IntegrityGuard {
  constructor({document,onSignal,isActive,Observer=globalThis.MutationObserver}){
    this.document=document;this.onSignal=onSignal;this.isActive=isActive;this.root=null;this.running=false;
    this.questionObserver=new Observer(()=>{
      if(this.root&&this.isActive()&&this.root.outerHTML!==this.baseline){
        this.pauseQuestions();this.onSignal('dom_tamper','Изменены элементы или текст вопросов');
      }
    });
    this.scriptObserver=new Observer(records=>{
      if(!this.isActive())return;
      if(this.root?.isConnected===false){this.pauseQuestions();this.onSignal('dom_tamper','Блок вопросов удалён со страницы');}
      for(const record of records){
        const nodes=record.type==='attributes'?[record.target]:Array.from(record.addedNodes||[]).flatMap(n=>[n,...(n.querySelectorAll?.('script')||[])]);
        if(nodes.some(executableScript)){this.onSignal('script_added','Добавлен или изменён исполняемый SCRIPT');break;}
      }
    });
    this.csp=event=>{if(this.running&&this.isActive())this.onSignal('csp_violation','Браузер заблокировал действие по Content Security Policy');};
    document.addEventListener('securitypolicyviolation',this.csp);
  }
  start(root,watchQuestions=true){
    if(!this.running){this.scriptObserver.observe(this.document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:['src','type']});this.running=true;}
    this.pauseQuestions();
    if(watchQuestions){this.root=root;this.baseline=root.outerHTML;this.questionObserver.observe(root,{childList:true,subtree:true,characterData:true,attributes:true});}
  }
  pauseQuestions(){this.questionObserver.disconnect();this.root=null;}
  stop(){this.pauseQuestions();this.scriptObserver.disconnect();this.running=false;}
  destroy(){this.stop();this.document.removeEventListener('securitypolicyviolation',this.csp);}
}

export function summarizeProbe(events,afterSeq,{startedAt,endedAt}){
  const signals=events.filter(e=>e.seq>afterSeq&&e.level==='warning');
  const incomplete=events.length>0&&events[0].seq>afterSeq+1;
  return {startedAt,endedAt,status:incomplete?'incomplete':signals.length?'events_observed':'no_browser_events',
    signals:signals.map(({type,seq})=>({type,seq})),
    conclusion:incomplete?'Часть журнала уже вытеснена. Повтори короткую пробу.':signals.length?'Браузер зафиксировал сигналы во время пробы. Причину нужно проверить.':'За время пробы браузерных сигналов не замечено. Запуск скрипта и скрытность не подтверждены.',
    osProcesses:'not_observable',osScreenshot:'not_observable',oesCompatibility:'not_tested'};
}
