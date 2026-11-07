"""Reproduce editor failure on the saved local state without changing the chat."""
import asyncio,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.document_drafting import prepare_document_draft, DraftPreparationError
from app.services.gigachat_client import get_gigachat_client

async def main():
    folder=Path(__file__).parent/'reported_housing_qa'
    payload=json.loads((folder/'source-state.json').read_text(encoding='utf-8'))
    state=payload['state']
    print('Saved failed fields:',state.get('draft_failure_fields'),flush=True)
    client=await get_gigachat_client(); original=client.chat_completion; traces=[]
    async def traced(*args,**kwargs):
        result=await original(*args,**kwargs)
        traces.append(dict(input=args[0],output=result.content))
        (folder/'editor-traces.json').write_text(json.dumps(traces,ensure_ascii=False,indent=2),encoding='utf-8')
        return result
    client.chat_completion=traced
    try:
        state,_=await prepare_document_draft(state,client)
        (folder/'verified-state.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Editor completed successfully.',flush=True)
    except DraftPreparationError as exc:
        (folder/'failure-state.json').write_text(json.dumps(exc.partial_state,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Failed fields:',exc.keys,flush=True)
        raise
if __name__=='__main__': asyncio.run(main())
