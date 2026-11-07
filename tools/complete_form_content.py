"""Authored legal paragraphs for the catalog, not questions pasted as text.

Values in {{slots}} belong to this case. Norms and layout are fixed separately.
Every form has its own subject, chronology, proof, remedy and signature roles.
"""

def b(text,role='body',when=None):
    return dict(text=text,role=role,when_field=when,when_status='filled' if when else None,when_value=None,when_values=None)


def section(title,*paragraphs):return [b(title,'heading'),*(b(p) if isinstance(p,str) else p for p in paragraphs)]


def body_for(key):
    if key in {'act_housing_handover','act_housing_return'}:
        returning=key=='act_housing_return'
        action='возвращает Наймодателю' if returning else 'передаёт Нанимателю'
        subject='Наниматель' if returning else 'Наймодатель'
        result=[b('Акт составлен во исполнение следующего договора найма: {{agreement}}.'),
            b(subject+' '+action+' жилое помещение по адресу: {{property}}. Характеристики помещения: {{property_description}}.'),
            b('Фактическая передача производится {{handover_date}}.'),
            *section('Состояние помещения и передаваемое имущество',
                'Состояние отделки, оборудования и выявленные недостатки зафиксированы следующим образом: {{condition}}.',
                'Вместе с помещением передаётся следующее имущество с указанными характеристиками и состоянием: {{inventory}}.',
                'На дату передачи зафиксированы следующие показания приборов учёта: {{meters}}.',
                'Передаваемые ключи и средства доступа: {{keys}}.'),
            *section('Замечания и результаты передачи','Замечания сторон к состоянию, комплектности и передаче: {{claims}}.')]
        if returning:result.append(b('Проведённые расчёты, возврат обеспечительного платежа и разногласия по удержаниям зафиксированы следующим образом: {{settlement}}.'))
        result.append(b('Стороны подтверждают передачу указанного помещения и перечисленного имущества в состоянии и количестве, отражённых в настоящем акте. Акт не подтверждает отсутствие иных требований, если они прямо не урегулированы сторонами.'))
        return result
    if key=='contract_housing_addendum':
        return [b('Стороны договорились изменить указанный договор найма: {{agreement}}.'),
            *section('Изменения договора','Изменяются следующие положения договора: {{changed_clauses}}.','Новая согласованная редакция условий: {{new_terms}}.'),
            b('Изменения применяются с {{effective_date}}.'),b('Количество экземпляров и их распределение между сторонами: {{copies}}.'),
            b('Остальные условия договора, не изменённые настоящим соглашением, сохраняют силу. Соглашение является неотъемлемой частью указанного договора.')]
    if key=='act_loan_receipt':
        return [b('Я, {{sender}}, адрес: {{sender_address}}, паспортные данные: {{borrower_details}}, подтверждаю получение денежных средств от займодавца {{recipient}}, адрес: {{recipient_address}}, паспортные данные: {{lender_details}}.'),
            b('Фактически полученная сумма займа составляет {{amount}}.'),b('{{transfer}}'),
            b('Денежные средства обязуюсь возвратить на следующих условиях: {{repayment}}.'),
            b('Согласованные условия о процентах: {{interest}}.'),b('Сведения об отдельном договоре займа: {{agreement}}.',when='agreement'),
            b('Настоящая расписка подтверждает изложенные сведения о получении денег и обязательстве их возврата. Суммы, не полученные заёмщиком, распиской не удостоверяются.')]
    if key.startswith('pretense_consumer_') or key=='claim_consumer':
        service=key.endswith('defective_service')
        result=[*section('Обстоятельства заказа услуг' if service else 'Обстоятельства приобретения','{{purchase}}','Уплаченная за приобретение сумма составляет {{amount}}.',
            'Оплата подтверждается следующими сведениями и документами: {{payment_evidence}}.')]
        personal='procedure' if key=='claim_consumer' else 'consumer_status'
        if personal!='procedure':result.append(b('Приобретение осуществлялось для следующих целей: {{consumer_status}}.'))
        if key.endswith('late_delivery'):
            result+=section('Нарушение срока передачи','Сторонами был согласован следующий срок передачи товара: {{delivery_due}}.','{{delivery_status}}')
        else:
            defect='defects' if key=='claim_consumer' else 'defect'
            category='category' if key=='claim_consumer' else ('service_description' if key.endswith('defective_service') else 'goods_category')
            label='Предмет заказанных работ или услуг' if service else ('Характеристики приобретённого товара, работ или услуг' if key=='claim_consumer' else 'Характеристики приобретённого товара')
            result+=section('Недостатки приобретения',label+': {{'+category+'}}.','{{'+defect+'}}',
                'Имеющиеся сведения и документы о недостатках: {{defect_evidence}}.')
        result+=[b('{{facts}}',when='facts'),b('Обращение к исполнителю' if service else 'Обращение к продавцу или исполнителю','heading','seller_response'),b('{{seller_response}}',when='seller_response')]
        if key!='claim_consumer':result+=[b('{{additional_claims}}',when='additional_claims')]
        return result
    if key=='complaint_consumer_agency':
        return [b('Жалоба подаётся в отношении продавца или исполнителя {{seller}}, находящегося по адресу: {{seller_address}}.'),
            *section('Обстоятельства нарушения','{{purchase}}','{{facts}}'),b('{{previous_contact}}',when='previous_contact')]
    if key in {'pretense_debt_loan','claim_debt_loan','claim_debt_services','claim_rent_deposit'}:
        result=[*section('Основание обязательства','{{agreement}}')]
        if key in {'pretense_debt_loan','claim_debt_loan'}:
            result+=[b('{{transfer}}'),b('Возврат займа должен был быть произведён в следующий срок или в следующем порядке: {{due_date}}.'),
                b('Фактически полученные в счёт возврата платежи: {{payments}}.')]
            if key=='claim_debt_loan':result.append(b('{{order_history}}',when='order_history'))
        elif key=='claim_debt_services':
            result+=[b('{{performance}}'),b('Согласованный срок оплаты: {{due_date}}.'),b('Фактически произведённая оплата: {{payments}}.')]
        else:
            result+=[b('Договор заключён в отношении жилого помещения по адресу: {{property}}.'),b('{{deposit_payment}}'),
                b('{{deposit_terms}}'),b('{{return_facts}}'),b('{{withholding}}')]
        result+=[b('На момент направления настоящего документа основная непогашенная сумма составляет {{amount}}.')]
        if key!='claim_rent_deposit':result.append(b('{{facts}}',when='facts'))
        return result
    if key in {'pretense_damage_flood','claim_damage_property'}:
        return [*section('Имущество и обстоятельства причинения ущерба','Повреждено следующее имущество: {{property}}.',
            'Право заявителя на имущество и основание требования подтверждаются следующими сведениями: {{property_right}}.',
            '{{event}}','{{responsibility}}'),
            *section('Повреждения и размер ущерба','Повреждения и утраты имущества: {{damage}}.','{{restoration}}',
                'Обстоятельства и размер ущерба подтверждаются следующими доказательствами: {{evidence}}.',
                'Размер заявленного основного ущерба составляет {{amount}}.')]
    if key in {'claim_labor_salary','pretense_labor_settlement'}:
        return [*section('Трудовые отношения и причитающиеся выплаты','{{employment}}',b('{{dismissal}}',when='dismissal'),
            b('Согласованные условия оплаты труда: {{wages}}.',when='wages'),'Период и состав невыплаченных сумм: {{debt_period}}.',
            'Основная задолженность работодателя перед работником составляет {{amount}}.'),
            *section('Подтверждения и обращение к работодателю','Имеющиеся документы и доказательства: {{evidence}}.',b('{{previous_contact}}',when='previous_contact')),
            *([b('{{salary_dispute}}',when='salary_dispute')] if key=='claim_labor_salary' else [])]
    if key=='claim_labor_reinstatement':
        return [*section('Трудовые отношения и увольнение','{{employment}}','{{dismissal_order}}','Копия приказа об увольнении получена в следующих обстоятельствах: {{notice_date}}.'),
            *section('Основания несогласия с увольнением','{{illegality}}','Обстоятельства подтверждаются следующими доказательствами: {{evidence}}.'),
            b('Сведения о среднем заработке и его расчёте: {{average_wage}}.'),b('{{term_reasons}}',when='term_reasons')]
    if key=='labor_resignation':
        return [b('Должность и подразделение работника: {{position}}.'),
            b('Прошу расторгнуть со мной трудовой договор по моей инициативе (по собственному желанию) {{last_day}}.'),
            b('{{early_reason}}',when='early_reason'),b('Сведения о дате и способе вручения заявления работодателю: {{delivery}}.')]
    if key in {'order_alimony','claim_alimony_share'}:
        return [*section('Сведения о ребёнке и родителях','Сведения о детях, на содержание которых заявляется требование: {{children}}.',
            '{{parentage}}','{{living}}',b('{{existing_support}}',when='existing_support'),b('{{other_dependants}}',when='other_dependants')),
            *section('Материальное содержание','{{assistance}}','Известные сведения о заработке и иных доходах обязанного родителя: {{income}}.',
                'Просимая доля заработка и иного дохода: {{share}}.','Начало периода, за который заявляется взыскание: {{start}}.'),
            *([b('{{eligibility}}',when='eligibility')] if key=='order_alimony' else [])]
    if key=='bailiff_alimony_arrears':
        return [b('Прошу рассмотреть заявление в рамках указанного исполнительного производства: {{enforcement}}.'),
            b('Сведения о должнике: {{debtor}}.'),b('Обязанность по уплате алиментов установлена следующим исполнительным документом: {{support_basis}}.'),
            b('Установленные размер, способ и сроки платежей: {{support_terms}}.'),
            b('Задолженность требуется определить за следующий период: {{arrears_period}}.'),
            b('Фактически полученные платежи с указанием дат и сумм: {{received_payments}}.'),
            b('Известные сведения о доходах должника и подтверждающих документах: {{income_information}}.')]
    if key=='claim_alimony_penalty':
        return [b('Обязанность ответчика по уплате алиментов установлена следующим документом: {{support_basis}}.'),
            b('Алименты установлены на содержание следующих детей: {{children}}.'),b('{{arrears_decision}}'),
            *section('Просроченные платежи и расчёт неустойки','Платежи, сроки их исполнения, просрочка и частичные оплаты: {{period_payments}}.',
                '{{fault}}','{{penalty_calculation}}')]
    if key=='claim_divorce':
        return [b('{{marriage}}'),b('Сведения об общих несовершеннолетних детях: {{children}}.'),
            *section('Обстоятельства прекращения семейных отношений','{{breakdown}}','{{registry_obstacle}}',b('{{restrictions}}',when='restrictions')),
            b('Позиция по связанным требованиям и наличию споров: {{disputes}}.')]
    if key.startswith('motion_'):
        result=[b('Настоящий документ подаётся по делу № {{case_number}}. Предмет рассматриваемого дела: {{case_subject}}.')]
        if key=='motion_postpone':result+=[b('Судебное заседание назначено на {{hearing_date}}.'),b('{{reasons}}'),b('Причины неявки подтверждаются следующими доказательствами: {{evidence}}.')]
        elif key=='motion_attach':result+=[b('Прошу приобщить следующие материалы:'),b('{{documents}}'),b('{{relevance}}'),b('{{timing}}',when='timing')]
        elif key=='motion_costs':result+=[b('{{outcome}}'),b('Судебный акт вступил в законную силу {{force_date}}.'),b('Состав и суммы понесённых судебных расходов: {{costs}}.'),b('Оплата и связь расходов с делом подтверждаются следующими документами: {{expense_proof}}.')]
        elif key=='motion_objection':result+=[b('Заявленные истцом требования: {{claims}}.'),*section('Возражения ответчика','{{objections}}','Позиция подтверждается следующими доказательствами: {{evidence}}.')]
        elif key=='motion_order_objection':result+=[b('Судебный приказ, относительно исполнения которого представлены возражения: {{order}}.'),b('{{received}}'),b('{{late_reasons}}',when='late_reasons'),b('{{disagreement}}')]
        elif key=='motion_restore_term':result+=[b('Пропущено совершение следующего процессуального действия: {{missed_action}}.'),b('Обстоятельства исчисления срока: {{deadline}}.'),b('{{reasons}}'),b('Причины пропуска подтверждаются следующими доказательствами: {{evidence}}.'),b('{{concurrent_action}}')]
        elif key=='motion_enforcement_writ':result+=[b('Судебный акт, подлежащий исполнению: {{decision}}.'),b('Сведения о вступлении акта в законную силу или основаниях немедленного исполнения: {{force_date}}.'),b('{{previous_writ}}',when='previous_writ'),b('Выбранный способ получения или направления исполнительного листа: {{delivery_method}}.')]
        return result
    if key=='complaint_bailiff_superior':
        return [b('Жалоба подаётся в порядке подчинённости в связи с исполнительным производством {{enforcement}}.'),
            b('Обжалуются постановления, действия или бездействие следующего должностного лица: {{official}}.'),
            *section('Обстоятельства и основания обжалования','{{challenged}}','О нарушении стало известно в следующих обстоятельствах: {{learned_date}}.','{{violation}}',b('{{late_reasons}}',when='late_reasons'))]
    if key=='power_of_attorney':
        return [b('Я, {{sender}}, адрес: {{sender_address}}, сведения, удостоверяющие личность: {{principal_details}}, настоящей доверенностью уполномочиваю представителя {{recipient}}, адрес: {{recipient_address}}, сведения, удостоверяющие личность: {{agent_details}}, совершать от моего имени следующие действия.'),
            *section('Полномочия представителя','{{powers}}'),b('Доверенность выдана на следующий срок: {{validity}}.'),
            b('Условия передоверия: {{substitution}}.'),b('Полномочия ограничены указанными действиями. Документ не передаёт личные неотчуждаемые права доверителя.')]
    raise KeyError('No complete form body: '+key)


PRESERVE={'contract_housing','contract_services','contract_work','contract_loan','claim_damage_flood'}

# Metadata controls intake/review; it is not a statement for the receiving body.
INTAKE_ONLY={'procedure','jurisdiction','copy_notice','copy_status','form_check','eligibility','order_history','salary_dispute','delivery'}
