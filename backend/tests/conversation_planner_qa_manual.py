import asyncio,json
from pathlib import Path
from app.services.document_workflow import new_state
from app.services.document_conversation import conversational_interview_turn

async def main():
    reports=[]
    for request in ['Нужен трудовой договор между детским садом и воспитателем','Нужен трудовой договор с бухгалтером ООО «Ромашка»','Нужна претензия за недоставленный диван, оплатила 85000 рублей']:
        state,answer,_=await conversational_interview_turn(new_state(request),request)
        print(request, '\n',state.get('question_origin'),state.get('last_questions'),answer,'error:',state.get('question_generation_error'),flush=True)
        assert state.get('question_origin')=='gigachat'
        assert 'Для школы' not in answer and answer.count('?')==1
        reports.append({'request':request,'state':state,'answer':answer})
    out=Path('/app/tests/conversation-planner-qa');out.mkdir(exist_ok=True)
    (out/'report.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':asyncio.run(main())
