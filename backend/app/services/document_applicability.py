"""Conservative procedure checks; no calculation or assumption from silence."""
import re


def applicability_issues(state):
    key=state.get('scenario','');fields=state.get('fields',{})
    def v(name):
        item=fields.get(name,{})
        return (item.get('value') or '').lower() if item.get('status')=='filled' else ''
    issues=[]
    def issue(field,question):issues.append(dict(field=field,code='form_applicability',question=question))
    if key=='order_alimony':
        if re.search(r'тв[её]рд|фиксирован|установ.{0,15}отцовств|оспарива',v('eligibility')+' '+v('share')) and not re.search(r'не (?:требуется|оспарива)|без (?:оспаривания|установления)',v('eligibility')):
            issue('eligibility','Указанные обстоятельства могут исключать приказной порядок. Уточните условия применения формы: для твёрдой суммы, спора об отцовстве или привлечения заинтересованных лиц требуется другой порядок. Какое именно требование готовим?')
    if key in {'order_alimony','claim_alimony_share','claim_alimony_fixed'}:
        existing=v('existing_support')
        # Negative statements can follow child/living facts in the same reply.
        # A mere mention of an absent agreement is not an existing instrument.
        existing=re.sub(r'(?:ранее )?алименты не устанавливались|(?:нотариального )?соглашения нет|(?:нотариально удостоверенное )?соглашение[^.;,]*не заключалось|судебного (?:акта|решения|приказа) нет','',existing)
        if existing and not re.match(r'^(?:нет|отсутств|не (?:было|установ|имеет|вынос|заключ))',existing) and re.search(r'решени|приказ|нотариальн|соглашен|исполнительн',existing):
            issue('existing_support','Алименты уже установлены указанным документом. Первоначальное назначение нельзя подставить вместо расчёта задолженности, изменения размера или неустойки. Уточните, что требуется, и укажите нужную форму обращения.')
    if key=='motion_enforcement_writ' and re.search(r'утер|утрачен|потер',v('previous_writ')):
        issue('previous_writ','Для утраченного исполнительного листа требуется заявление о выдаче дубликата и отдельные основания. Эта форма предназначена для первоначальной выдачи. Уточните, выдавался ли лист и что с ним произошло?')
    if key=='act_loan_receipt' and re.search(r'ещ[её] не (?:передан|получен)|пока не (?:передан|получен)|передам|будут переданы',v('transfer')):
        issue('transfer','Расписка удостоверяет уже состоявшееся получение денег. Деньги фактически переданы заёмщику или пока только планируются к передаче?')
    if key=='contract_housing' and re.search(r'\b(?:ооо|ао|пао|ип)\b',v('recipient')):
        issue('recipient','Эта форма найма предназначена для проживания гражданина. Наниматель — гражданин или помещение получает организация по договору аренды?')
    return issues
