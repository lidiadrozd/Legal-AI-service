"""Fill trusted OOXML content controls without rebuilding the document layout."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from lxml import etree
from app.services.document_template_library import TEMPLATE_ROOT, format_template_fields, strip_template_label_echo

ASSET_ROOT = TEMPLATE_ROOT.parent / 'assets'
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W}


def _asset(relative, digest):
    path = (ASSET_ROOT / relative).resolve()
    if not path.is_relative_to(ASSET_ROOT.resolve()) or not path.is_file():
        raise ValueError('Missing or invalid DOCX template asset')
    data = path.read_bytes()
    if sha256(data).hexdigest() != digest:
        raise ValueError('DOCX template asset checksum mismatch')
    return data


def load_docx_asset(package, scenario):
    asset = package['docx_asset']
    original = _asset(asset['template'], asset['template_sha256'])
    schema = json.loads(_asset(asset['schema'], asset['schema_sha256']))
    if schema['scenario'] != scenario.key or schema['version'] != package['version']:
        raise ValueError('DOCX template does not match selected scenario/version')
    if schema.get('blocks_sha256') and schema['blocks_sha256'] != sha256(json.dumps(package['blocks'],ensure_ascii=False,sort_keys=True).encode()).hexdigest():
        raise ValueError('DOCX asset and declarative form content differ')
    if set(schema['fields']) - {f.key for f in scenario.fields}:
        raise ValueError('Unknown DOCX field')
    return original, schema


def _tag(node):
    found = node.find('w:sdtPr/w:tag', NS)
    return found.get('{'+W+'}val', '') if found is not None else ''


def _requisite(value):
    # These are list separators and explicit educational annotations, not
    # passport data. Preserve every supplied identifier and substantive note.
    value = re.sub(r'\(где первые \d+ цифры[^)]*\)', '', value, flags=re.I)
    value = re.sub(r'\(\s*(?=•|$)', '', value)
    return '\n'.join(part.strip(' \n•') for part in re.split(r'[•\n]+', value) if part.strip(' \n•'))


def _value(key, values, schema, specs):
    value = values.get(key) or '[' + specs[key].label.lower() + ']'
    form = schema['fields'][key].get('format', 'plain')
    value = value.strip()
    if re.fullmatch(r'\[[^\]]+\]',value):return value
    if key=='contacts':return value.rstrip(' .')
    value = re.sub(r'\b(пункт(?:ом|а|е)?|п\.)\s+[XYХУ](?=\W|$)',r'\1 [номер пункта]',value,flags=re.I)
    if form == 'requisite': return _requisite(value)
    if form == 'phrase': return value.rstrip('.')
    if form == 'sentence':
        value = value[:1].upper() + value[1:]
        if value.endswith('.'): value=value.rstrip('.')+'.'
        return value if value.endswith(('.', '!', '?')) else value + '.'
    return value


def docx_review_fields(fields):
    """Unresolved imported references are visible blanks, not verified clauses."""
    pattern=r'\b(?:пункт(?:ом|а|е)?|п\.)\s+[XYХУ](?=\W|$)'
    return [key for key,stored in fields.items() if stored.get('status')=='filled'
            and re.search(pattern,stored.get('value') or '',re.I)]


def _write_inline(control, value):
    following=control.getnext()
    # The template owns closing punctuation. A supplied final full stop must
    # not create an invalid combination such as ".," across adjacent runs.
    if value.endswith('.') and following is not None and following.tag=='{'+W+'}r':
        suffix=''.join(following.xpath('.//w:t/text()',namespaces=NS)).lstrip()
        if suffix.startswith(('.', ',', ';', ':', '!', '?')): value=value[:-1]
    content = control.find('w:sdtContent', NS)
    prototype = content.find('.//w:rPr', NS)
    prototype = deepcopy(prototype) if prototype is not None else None
    for child in list(content): content.remove(child)
    for index, line in enumerate(value.split('\n')):
        run = etree.SubElement(content, '{'+W+'}r')
        if prototype is not None: run.append(deepcopy(prototype))
        if index: etree.SubElement(run, '{'+W+'}br')
        text = etree.SubElement(run, '{'+W+'}t')
        text.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
        text.text = line


def _literal_prefix_before_control(control):
    """Return literal template text immediately to the left of a slot.

    Content controls in the maintained DOCX assets sit next to normal Word
    runs.  Stop at the preceding content control: its value is data, whereas
    the remaining runs are the fixed wrapper owned by the template.
    """
    parts=[]
    sibling=control.getprevious()
    while sibling is not None:
        if sibling.tag=='{'+W+'}sdt':
            break
        parts.append(''.join(sibling.xpath('.//w:t/text()',namespaces=NS)))
        sibling=sibling.getprevious()
    return ''.join(reversed(parts))


def _write_paragraphs(control, value, rule):
    paragraph = control.getparent()
    if paragraph.tag != '{'+W+'}p': raise ValueError('Paragraph field must belong to a paragraph')
    # User list markers belong to their answer, not to the contract's
    # section numbering. Generate stable subparagraphs from the template rule.
    lines = [(line if rule.get('preserve_list_numbers') else re.sub(r'^\s*(?:[•–—-]\s*|\d+(?:\.\d+)*[.)]\s+)', '', line)).strip()
             for line in re.split(r'\n+|\s*•\s*', value) if line.strip()]
    if not lines: lines=['']
    parent = paragraph.getparent(); position=parent.index(paragraph)
    prefix = ''.join(paragraph.xpath('./w:r/w:t/text()',namespaces=NS))
    # A content-control list is frequently followed by the template's
    # sentence-ending full stop. When we split it into numbered paragraphs,
    # that full stop belongs to neither the heading nor the first item.
    if rule.get('preserve_list_numbers') and prefix.rstrip().endswith('.'):
        prefix = prefix.rstrip()[:-1]
    clause_index=0
    for index,line in enumerate(lines):
        clone = deepcopy(paragraph)
        for child in list(clone):
            if child.tag != '{'+W+'}pPr': clone.remove(child)
        is_heading=(rule.get('paragraph_headings') and line.endswith(':')
                    and len(line)<100 and len(line.split())<=8
                    and not re.search(r'\d|[.!?;]',line))
        if is_heading:
            lead=''
        elif rule.get('paragraph_section'):
            clause_index+=1
            lead=rule['paragraph_section']+'.'+str(clause_index)+'. '
        elif index and rule.get('paragraph_number'):
            lead=rule['paragraph_number']+'.'+str(index)+'. '
        elif index and rule.get('preserve_list_numbers'):
            # The item already carries its own number. A text lead such as
            # "Приложения: " is a heading and belongs only to the first item.
            lead=''
        else: lead=prefix
        run=etree.SubElement(clone,'{'+W+'}r');text=etree.SubElement(run,'{'+W+'}t')
        text.set('{http://www.w3.org/XML/1998/namespace}space','preserve');text.text=lead
        slot=deepcopy(control);_write_inline(slot,line);clone.append(slot)
        if is_heading:
            properties=clone.find('w:pPr',NS)
            if properties is None: properties=etree.SubElement(clone,'{'+W+'}pPr')
            keep=properties.find('w:keepNext',NS)
            if keep is None: keep=etree.SubElement(properties,'{'+W+'}keepNext')
            keep.set('{'+W+'}val','1')
            alignment=properties.find('w:jc',NS)
            if alignment is None: alignment=etree.SubElement(properties,'{'+W+'}jc')
            alignment.set('{'+W+'}val','left')
            for item in clone.xpath('.//w:r',namespaces=NS):
                run_properties=item.find('w:rPr',NS)
                if run_properties is None:
                    run_properties=etree.Element('{'+W+'}rPr');item.insert(0,run_properties)
                bold=etree.SubElement(run_properties,'{'+W+'}b');bold.set('{'+W+'}val','1')
        parent.insert(position+index,clone)
    parent.remove(paragraph)


def _condition(name, fields, schema):
    rule = schema['conditions'][name]
    stored = fields.get(rule['field'], {})
    if rule.get('unknown'): return stored.get('status') != 'filled'
    if stored.get('status') != 'filled': return False
    if rule.get('values') is not None: return stored.get('value') in rule['values']
    return rule.get('value') is None or stored.get('value') == rule['value']


def _is_page_field(element):
    return element.tag == qn('w:fldSimple') and 'PAGE' in element.get(qn('w:instr'), '').upper()


def _apply_standard_page_numbering(payload):
    """Move the maintained templates' PAGE field to the standard upper position."""
    document = Document(BytesIO(payload))
    for section in document.sections:
        footer_fields = [field for field in section.footer._element.iter(qn('w:fldSimple')) if _is_page_field(field)]
        if not footer_fields:
            continue

        # ГОСТ Р 7.0.97-2025: number multi-page documents from page two,
        # centered in the upper field, 10 mm from the upper page edge.
        section.different_first_page_header_footer = True
        section.header_distance = Cm(1)
        header = section.header
        target = header.paragraphs[0]
        if ''.join(target._element.itertext()).strip() or any(target._element.iter(qn('w:fldSimple'))):
            target = header.add_paragraph()
        target.alignment = WD_ALIGN_PARAGRAPH.CENTER
        target.paragraph_format.space_before = Pt(0)
        target.paragraph_format.space_after = Pt(0)
        target._p.append(deepcopy(footer_fields[0]))

        # Leave any non-page footer text intact; template page fields are the
        # only content moved to the header.
        for field in footer_fields:
            field.getparent().remove(field)

    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _stable_docx_archive(payload):
    """Normalise ZIP timestamps after python-docx has saved the package.

    The document body is deterministic, but ``python-docx`` writes current
    ZIP entry timestamps.  That made a DOCX regenerated seconds later differ
    byte-for-byte even though the PDF converter received the same document.
    Stable timestamps make caching and the export invariant reliable without
    changing any OOXML content.
    """
    output = BytesIO()
    with ZipFile(BytesIO(payload)) as source, ZipFile(output, 'w', ZIP_DEFLATED) as target:
        for item in source.infolist():
            # Keep entry name, attributes and order; only the volatile time is
            # replaced with the earliest ZIP-supported timestamp.
            item.date_time = (1980, 1, 1, 0, 0, 0)
            target.writestr(item, source.read(item.filename))
    return output.getvalue()


def fill_docx_template(package, scenario, fields):
    original, schema = load_docx_asset(package, scenario)
    values = format_template_fields(scenario, fields)
    specs = {f.key:f for f in scenario.fields}
    output = BytesIO()
    with ZipFile(BytesIO(original)) as source, ZipFile(output,'w',ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename.startswith('word/') and item.filename.endswith('.xml'):
                root = etree.fromstring(data)
                # Whole OOXML blocks are removed for conditional branches;
                # adjacent styles, numbering, tables and section properties stay.
                for control in list(root.xpath('//w:sdt', namespaces=NS)):
                    tag = _tag(control)
                    if tag.startswith('if:'):
                        name = tag[3:]
                        if name not in schema['conditions']: raise ValueError('Unknown DOCX condition')
                        if not _condition(name, fields, schema):
                            control.getparent().remove(control)
                for control in root.xpath('//w:sdt', namespaces=NS):
                    tag = _tag(control)
                    if tag.startswith('field:'):
                        key = tag[6:]
                        if key not in schema['fields']: raise ValueError('Unknown DOCX content control')
                        if key in package.get('intake_only_fields',()):
                            # A legacy DOCX can still contain a control for
                            # questionnaire-only metadata.  Remove its whole
                            # paragraph when possible so neither a label nor a
                            # fallback placeholder remains visible.
                            paragraph=control.getparent()
                            if paragraph is not None and paragraph.tag=='{'+W+'}p':
                                paragraph.getparent().remove(paragraph)
                            else:
                                _write_inline(control,'')
                            continue
                        rule=schema['fields'][key]
                        value=_value(key, values, schema, specs)
                        # Keep DOCX output consistent with the text/PDF
                        # pipeline.  Previously this safeguard existed only
                        # in render_package_blocks, so a model echo such as
                        # "Исполнение обязательств: ..." was duplicated in
                        # the downloaded Word file.
                        value=strip_template_label_echo(value,_literal_prefix_before_control(control))
                        if rule.get('paragraph_number') or rule.get('paragraph_section') or rule.get('paragraph_lines'):
                            _write_paragraphs(control,value,rule)
                        else: _write_inline(control,value)
                # Deliver ordinary editable paragraphs/runs. This also keeps
                # exported text readable by upload extractors such as python-docx.
                for control in reversed(root.xpath('//w:sdt', namespaces=NS)):
                    parent = control.getparent()
                    content = control.find('w:sdtContent',NS)
                    position = parent.index(control)
                    for child in list(content):
                        parent.insert(position,child); position += 1
                    parent.remove(control)
                if '{{' in ''.join(root.itertext()): raise ValueError('Unfilled DOCX template control')
                data = etree.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
            target.writestr(item,data)
    return _stable_docx_archive(_apply_standard_page_numbering(output.getvalue()))


def docx_to_pdf(payload, *, executable=None):
    converter = executable or shutil.which('libreoffice') or shutil.which('soffice')
    if not converter: raise RuntimeError('Для PDF требуется конвертер DOCX. Файл DOCX доступен отдельно.')
    with tempfile.TemporaryDirectory(prefix='legal-docx-') as folder:
        directory = Path(folder)
        source = directory/'document.docx'; source.write_bytes(payload)
        profile = (directory/'profile').as_uri()
        try:
            subprocess.run([converter, '-env:UserInstallation='+profile, '--headless',
                '--convert-to','pdf:writer_pdf_Export','--outdir',str(directory),str(source)],
                check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
        except (subprocess.SubprocessError,OSError) as exc:
            raise RuntimeError('Не удалось преобразовать DOCX в PDF. Исходные ответы сохранены; доступен формат DOCX.') from exc
        result = directory/'document.pdf'
        if not result.is_file() or not result.read_bytes().startswith(b'%PDF-'):
            raise RuntimeError('Конвертер не создал PDF из DOCX.')
        return result.read_bytes()
