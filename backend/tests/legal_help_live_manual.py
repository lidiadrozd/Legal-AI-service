"""Live acceptance of sourced explanations. Synthetic data, no account writes."""
import asyncio,json
from pathlib import Path
from complete_form_cases import make_state
from app.services.document_conversation import conversational_interview_turn
from app.services.document_question_policy import asks_user_to_determine_law

async def main():
    reports=[]
    for key,message in [('work_conditions','Стандартные условия регулируются законодательством. Сам посмотри'),('compensations','я не знаю, ты скажи'),('leave_context','посмотри сам закон и скажи')]:
        state=make_state('contract_employment');state['request']='Трудовой договор между детским садом и воспитателем'
        state['fields']['position']['value']='воспитатель'
        state['fields']['sender']['value']='Детский сад «Пример»'
        state['fields'].pop(key);state['fields'].pop('vacation')
        state.update(phase='collecting',last_questions=[key])
        result,answer,usage=await conversational_interview_turn(state,message)
        print(key,result.get('question_origin'),answer,'error:',result.get('question_generation_error'),flush=True)
        assert result.get('question_origin')=='gigachat'
        assert result['fields'].get(key,{}).get('value')!=message
        assert not asks_user_to_determine_law(answer.split('\n\n')[-1])
        assert len(answer)>100 and answer.count('?')==1
        reports.append(dict(field=key,answer=answer,tokens=usage.total_tokens))
    out=Path('/app/tests/catalog-audit-2026-10-29')
    (out/'live-help.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':asyncio.run(main())
