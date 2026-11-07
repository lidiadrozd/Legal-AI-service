from copy import deepcopy
from io import BytesIO

from docx import Document

from app.services.document_case_facts import set_field
from app.services.document_docx_template import fill_docx_template
from app.services.document_form_composition import (
    form_narrative_keys,
    form_presentation_fields,
    local_candidate,
)
from app.services.document_form_intake import _collect_damage_property_narrative
from app.services.document_scenarios import SCENARIOS
from app.services.document_template_library import load_text_package
from app.services.document_workflow import new_state
from complete_form_cases import make_state


RICH_DAMAGE_ACCOUNT = (
    "14 августа 2026 года из-за прорыва трубы в подъезде была затоплена моя "
    "квартира по адресу: г. Екатеринбург, ул. Мира, д. 55, кв. 67. "
    "Я собственник квартиры, это подтверждается выпиской ЕГРН. "
    "Управляющая компания ООО «ДомСервис» составила акт о заливе, но добровольно "
    "ущерб не возместила. Стоимость восстановительного ремонта по отчёту оценщика "
    "составляет 138 400 рублей. За оценку я заплатила 7 000 рублей, почтовые расходы "
    "на претензию составили 550 рублей. Претензию в управляющую компанию направила "
    "1 сентября 2026 года, ответа не получила."
)


def test_dense_damage_account_is_split_before_a_short_property_slot_is_saved():
    state = new_state("Иск о возмещении ущерба")
    state.update(scenario="claim_damage_property", fields={})

    def put(key, value, evidence, status="filled"):
        set_field(state, key, value, evidence, status)

    consumed = _collect_damage_property_narrative(state, RICH_DAMAGE_ACCOUNT, "property", put)

    assert {"property", "property_right", "event", "responsibility", "restoration", "pretrial", "amount"} <= consumed
    assert state["fields"]["property"]["value"] == (
        "моя квартира по адресу: г. Екатеринбург, ул. Мира, д. 55, кв. 67"
    )
    assert "Стоимость восстановительного" not in state["fields"]["property"]["value"]
    assert state["fields"]["restoration"]["value"].startswith(
        "Стоимость восстановительного ремонта"
    )
    assert state["fields"]["pretrial"]["value"].startswith("Претензию в управляющую компанию")
    assert state["fields"]["amount"]["value"] == "138400.00"


def test_legacy_dense_property_story_is_rendered_as_separate_template_paragraphs():
    state = make_state("claim_damage_property")
    state["fields"]["property"].update(
        value=RICH_DAMAGE_ACCOUNT,
        original=RICH_DAMAGE_ACCOUNT,
        evidence=RICH_DAMAGE_ACCOUNT,
    )
    state["fields"]["restoration"].update(
        value=(
            "Стоимость восстановительного ремонта по отчёту оценщика составляет 138 400 рублей. "
            "Расходы на оценку составили 7 000 рублей."
        )
    )
    # Simulate a completed offline/legacy draft.  The render-time guard must
    # work even when a previous interview had already saved the long answer.
    state["draft_fields"] = {
        key: deepcopy(field["value"])
        for key, field in state["fields"].items()
        if key in form_narrative_keys(state) and field.get("status") == "filled"
    }

    assert local_candidate("property", RICH_DAMAGE_ACCOUNT, "phrase", "claim_damage_property") is None
    fields = form_presentation_fields(state)
    document = Document(
        BytesIO(fill_docx_template(load_text_package(SCENARIOS["claim_damage_property"]), SCENARIOS["claim_damage_property"], fields))
    )
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    property_paragraph = next(item for item in paragraphs if item.startswith("Повреждено следующее имущество:"))
    restoration_paragraph = next(item for item in paragraphs if item.startswith("Стоимость восстановительного ремонта"))

    assert property_paragraph.endswith("кв. 67.")
    assert "Стоимость восстановительного" not in property_paragraph
    assert "138 400 рублей" in restoration_paragraph
