"""Resolve extraction against user text, independent of model evidence labels."""
import re


def source_sentences(text):
    from app.services.document_form_intake import _protect_abbreviations
    # Abbreviations and decimal/date dots are not sentence boundaries.
    protected=_protect_abbreviations(text)
    return [part.replace('\uFFF0','.').strip() for part in
            re.split(r'(?<=[.!?;])\s+|\n+',protected) if part.strip()]


def literal_evidence(quote,message,evidence=''):
    """Return the literal value and containing source clause, or no match.

    A model may return `latest_message` as evidence. That is neither a fact
    nor grounds to discard a real quote: the original turn is authoritative.
    Ambiguous repeated values require a valid explicit evidence fragment.
    """
    if not quote or not isinstance(quote,str):return None
    def pattern(value):
        return r'\s+'.join(re.escape(token).replace('ё','[её]').replace('Ё','[ЕЁ]')
                          for token in value.split())
    matches=list(re.finditer(pattern(quote),message,re.I))
    if not matches:return None
    if evidence and evidence.strip() and evidence.strip().casefold()!=quote.strip().casefold():
        for bound in re.finditer(pattern(evidence),message,re.I):
            selected=[m for m in matches if bound.start()<=m.start() and m.end()<=bound.end()]
            if len(selected)==1:return selected[0][0],bound[0]
    # Sentence context establishes roles such as "Истец — ..." without
    # copying a nearby person's address into the same proof fragment.
    candidates=[]
    for sentence in source_sentences(message):
        found=list(re.finditer(pattern(quote),sentence,re.I))
        if len(found)==1:candidates.append((found[0][0],sentence))
    unique=list(dict.fromkeys(candidates))
    if len(unique)==1:return unique[0]
    if len(matches)==1:return matches[0][0],matches[0][0]
    return None
