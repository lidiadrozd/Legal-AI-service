from app.services.answer_norms import extract_answer_norms, answer_references, heading_document_key, TK_KEY, GK_KEY
from app.services.legal_sources import NormIdentity


def norms(text):
    return [r["legal_source"].norm for r in extract_answer_norms(text)]


def test_same_article_in_different_laws_is_distinct():
    assert norms("Статья 10 ТК РФ. Статья 10 ГК РФ.") == [NormIdentity(TK_KEY, "10"), NormIdentity(GK_KEY, "10")]


def test_unidentified_article_and_ambiguous_civil_code_part_are_skipped():
    assert norms("Статья 10. Статья 9999 ГК РФ.") == []


def test_full_code_name_part_and_duplicates():
    assert norms("Часть 2 статьи 10 Трудового кодекса Российской Федерации. ТК РФ: статья 10.") == [NormIdentity(TK_KEY, "10", "2"), NormIdentity(TK_KEY, "10")]
    assert len(norms("ст. 10 ТК РФ; ТК РФ статья 10")) == 1


def test_number_and_issue_date_identify_law_without_catalog():
    assert norms("Статья 4 Федерального закона от 03.06.2009 № 103-ФЗ.") == [NormIdentity("ru:103-fz:2009-06-03", "4")]
    assert norms("Закон от 01.01.2020 № 10-ФЗ: статья 5.") == [NormIdentity("ru:10-fz:2020-01-01", "5")]
    assert norms("Закон от 31.02.2020 № 10-ФЗ") == []
    assert heading_document_key('Закон от 01.01.2021 N 10-ФЗ') != heading_document_key('Закон от 01.01.2020 N 10-ФЗ')


def test_whole_law_is_preserved_without_inventing_article():
    assert norms("Ответ основан на ТК РФ и Законе от 03.06.2009 № 103-ФЗ.") == [NormIdentity("ru:103-fz:2009-06-03"), NormIdentity(TK_KEY)]


def test_references_work_without_rag_sources():
    assert answer_references("Статья 10 ТК РФ", ())[0]["legal_source"].norm == NormIdentity(TK_KEY, "10")


def test_civil_code_parts_have_their_own_original_act():
    assert norms("Статья 687 ГК РФ") == [NormIdentity("ru:14-fz:1996-01-26", "687")]
    assert norms("Статья 1111 ГК РФ") == [NormIdentity("ru:146-fz:2001-11-26", "1111")]
    assert norms("Статья 1250 ГК РФ") == [NormIdentity("ru:230-fz:2006-12-18", "1250")]


def test_consumer_act_number_and_named_reference():
    from app.services.answer_norms import ZPP_KEY
    assert heading_document_key('Закон РФ от 07.02.1992 N 2300-1') == ZPP_KEY
    assert norms('Статья 18 Закона РФ «О защите прав потребителей»') == [NormIdentity(ZPP_KEY, "18")]
    assert norms('Закон РФ «О защите прав потребителей». Статья 18 указанного закона.') == [NormIdentity(ZPP_KEY, "18")]


def test_anaphor_never_guesses_between_two_laws_or_bare_articles():
    assert norms('ТК РФ и Закон РФ «О защите прав потребителей». Статья 18 указанного закона.')[0].article == ""
    assert all(n.article == "" for n in norms('ТК РФ и Закон РФ «О защите прав потребителей». Статья 18 указанного закона.'))
    assert all(n.article == "" for n in norms('ТК РФ. Статья 10.'))
