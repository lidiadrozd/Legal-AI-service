import json
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from starlette.exceptions import HTTPException as RouteException
from starlette.requests import Request
from sqlalchemy import select,func
from app.models.chat import ChatSession,Message
from app.services.llm_cost import TokenUsage


@pytest.mark.asyncio
async def test_resource_404_keeps_recovery_code_and_route_404_stays_distinct():
    from app.main import not_found_handler
    request=Request({'type':'http','path':'/documents/interviews','headers':[]})
    response=await not_found_handler(request,HTTPException(404,detail={'code':'chat_context_unavailable','message':'Выбранный чат недоступен'}))
    assert json.loads(response.body)['error']['code']=='chat_context_unavailable'
    missing=await not_found_handler(request,RouteException(404,detail='Not Found'))
    assert json.loads(missing.body)['error']=='Endpoint не найден'


@pytest.mark.asyncio
@pytest.mark.parametrize('foreign',[False,True])
async def test_missing_or_foreign_context_creates_nothing_and_can_restart_safely(client,db_session,monkeypatch,foreign):
    from app.main import not_found_handler
    client._transport.app.add_exception_handler(404,not_found_handler)
    private=ChatSession(user_id=2,title='private')
    db_session.add(private);await db_session.flush()
    db_session.add(Message(chat_id=private.id,role='user',content='PRIVATE_CONTEXT_MUST_NOT_BE_READ'))
    await db_session.commit()
    before=await db_session.scalar(select(func.count()).select_from(ChatSession))
    context_id=private.id if foreign else 999999
    advance=AsyncMock(return_value=({'phase':'collecting','scenario':None,'fields':{},'last_questions':[]},'Какой документ нужен?',TokenUsage(0,0,0,False)))
    monkeypatch.setattr('app.services.document_workflow.advance_interview',advance)
    payload={'prompt':'После выезда не возвращён обеспечительный платёж 35000 рублей. Хочу составить иск.','chat_id':context_id}
    rejected=await client.post('/documents/interviews',json=payload)
    assert rejected.status_code==404
    assert rejected.json()['error']['code']=='chat_context_unavailable'
    assert await db_session.scalar(select(func.count()).select_from(ChatSession))==before
    advance.assert_not_called()
    restarted=await client.post('/documents/interviews',json={'prompt':payload['prompt']})
    assert restarted.status_code==201,restarted.text
    assert await db_session.scalar(select(func.count()).select_from(ChatSession))==before+1
    saved=await db_session.get(ChatSession,restarted.json()['chat_id'])
    assert saved.user_id==1
    call=advance.await_args.args[0]
    assert call['context']=='' and call['request']==payload['prompt']
