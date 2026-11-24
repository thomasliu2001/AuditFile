# -*- coding: utf-8 -*-
"""零依赖 .docx 解析：章节层级、正文、表格、图片、页眉页脚、字体字号、文档属性。"""
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DC = "{http://purl.org/dc/elements/1.1/}"
CP = "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}"

HEADING_STYLE_RE = re.compile(r"(?:heading|标题)\s*([1-9])", re.IGNORECASE)
NUMBER_HEAD_RE = re.compile(r"^(\d+(?:\.\d+){0,5})(?:[\.、．]|\s)+(\S.*)$")
END_PUNCT = ("。", "；", "，", ",", "；", ":", "：")


def _text_of(node):
    return "".join(t.text or "" for t in node.iter(W + "t"))


def _parse_styles(zf):
    styles = {}
    if "word/styles.xml" not in zf.namelist():
        return styles
    try:
        root = ET.fromstring(zf.read("word/styles.xml"))
    except ET.ParseError:
        return styles

    for st in root.findall(W + "style"):
        sid = st.get(W + "styleId") or ""
        name_el = st.find(W + "name")
        name = name_el.get(W + "val") if name_el is not None else ""
        level = 0
        m = HEADING_STYLE_RE.search(name or "")
        if m:
            level = int(m.group(1))
        if not level:
            ol = st.find(W + "pPr/" + W + "outlineLvl")
            if ol is not None:
                try:
                    level = int(ol.get(W + "val")) + 1
                except (TypeError, ValueError):
                    level = 0
        styles[sid] = {"name": name, "level": level}
    return styles


def _parse_paragraph(p, index, styles):
    text = _text_of(p).strip()
    style_id = ""
    level = 0
    ppr = p.find(W + "pPr")
    if ppr is not None:
        st = ppr.find(W + "pStyle")
        if st is not None:
            style_id = st.get(W + "val") or ""
        ol = ppr.find(W + "outlineLvl")
        if ol is not None and not level:
            try:
                level = int(ol.get(W + "val")) + 1
            except (TypeError, ValueError):
                level = 0

    style_info = styles.get(style_id, {})
    style_name = style_info.get("name", "")
    if not level:
        level = style_info.get("level", 0)
    if not level and style_name:
        m = HEADING_STYLE_RE.search(style_name)
        if m:
            level = int(m.group(1))

    fonts = Counter()
    sizes = Counter()
    for run in p.findall(W + "r"):
        run_text = "".join(t.text or "" for t in run.findall(W + "t"))
        if not run_text.strip():
            continue
        rpr = run.find(W + "rPr")
        if rpr is not None:
            rf = rpr.find(W + "rFonts")
            if rf is not None:
                font = rf.get(W + "eastAsia") or rf.get(W + "ascii")
                if font:
                    fonts[font] += len(run_text)
            sz = rpr.find(W + "sz")
            if sz is not None:
                try:
                    sizes[int(sz.get(W + "val")) / 2.0] += len(run_text)
                except (TypeError, ValueError):
                    pass

    numbering = ""
    if text:
        m = NUMBER_HEAD_RE.match(text)
        if m:
            numbering = m.group(1)

    return {
        "index": index,
        "text": text,
        "style_id": style_id,
        "style_name": style_name,
        "level": level,
        "is_heading": bool(level and text),
        "numbering": numbering,
        "fonts": dict(fonts),
        "sizes": {str(k): v for k, v in sizes.items()},
    }


def _fallback_heading(p):
    """无标题样式时，用“1.1 标题”这类编号识别中文章节。"""
    text = p["text"]
    if not text or len(text) > 40 or p["level"]:
        return 0
    if text.endswith(END_PUNCT):
        return 0
    m = NUMBER_HEAD_RE.match(text)
    if not m:
        return 0
    title = m.group(2).strip()
    if not title or title[0].isdigit():
        return 0
    return len(m.group(1).split("."))


def _build_sections(blocks):
    """按文档流顺序构建章节：表格内容计入所属章节正文，避免误判空章节。"""
    sections = []
    for i, block in enumerate(blocks):
        if block["kind"] != "p" or not block["level"]:
            continue
        level = block["level"]
        body = []
        children = []
        for nxt in blocks[i + 1:]:
            if nxt["kind"] == "p" and nxt["level"]:
                if nxt["level"] <= level:
                    break
                children.append(nxt["text"])
            elif nxt["text"]:
                body.append(nxt["text"])
        sections.append({
            "title": block["text"],
            "level": level,
            "body": "\n".join(body),
            "children": children,
        })
    return sections


def _read_header_footer(zf, names, prefix):
    texts = []
    count = 0
    has_page_field = False
    for name in names:
        if not name.startswith(prefix):
            continue
        count += 1
        try:
            root = ET.fromstring(zf.read(name))
        except ET.ParseError:
            continue
        texts.append(_text_of(root).strip())
        for node in root.iter(W + "instrText"):
            if "PAGE" in (node.text or "").upper():
                has_page_field = True
        for node in root.iter(W + "fldSimple"):
            if "PAGE" in (node.get(W + "instr") or "").upper():
                has_page_field = True
    return {"count": count, "text": " ".join(t for t in texts if t), "has_page_field": has_page_field}


def _read_core_props(zf):
    props = {"title": "", "author": "", "subject": "", "keywords": "", "last_modified_by": ""}
    if "docProps/core.xml" not in zf.namelist():
        return props
    try:
        root = ET.fromstring(zf.read("docProps/core.xml"))
    except ET.ParseError:
        return props
    mapping = {
        "title": DC + "title",
        "author": DC + "creator",
        "subject": DC + "subject",
        "keywords": CP + "keywords",
        "last_modified_by": CP + "lastModifiedBy",
    }
    for key, tag in mapping.items():
        node = root.find(tag)
        if node is not None and node.text:
            props[key] = node.text.strip()
    return props


def _count_words(text):
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z0-9_]+", text))
    return chinese + latin


def parse_docx(data):
    """解析 docx 二进制内容，返回结构化文档模型。解析失败抛 ValueError。"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception as exc:
        raise ValueError("不是有效的 .docx 文件（无法解包）：%s" % exc)

    names = zf.namelist()
    if "word/document.xml" not in names:
        raise ValueError("文件缺少 word/document.xml，可能是旧版 .doc 或已损坏，请另存为 .docx")
    try:
        root = ET.fromstring(zf.read("word/document.xml"))
    except ET.ParseError as exc:
        raise ValueError("word/document.xml 解析失败：%s" % exc)

    body = root.find(W + "body")
    if body is None:
        raise ValueError("文档缺少 body 节点")

    styles = _parse_styles(zf)
    paragraphs = []
    blocks = []
    tables = 0
    figures = 0
    table_texts = []
    images = set()

    for child in body:
        if child.tag == W + "p":
            paragraph = _parse_paragraph(child, len(paragraphs), styles)
            paragraphs.append(paragraph)
            blocks.append({"kind": "p", "text": paragraph["text"], "level": 0, "ref": paragraph})
        elif child.tag == W + "tbl":
            tables += 1
            cells = []
            for cell in child.iter(W + "tc"):
                cell_text = _text_of(cell).strip()
                if cell_text:
                    cells.append(cell_text)
            joined = " | ".join(cells)
            table_texts.append(joined)
            blocks.append({"kind": "tbl", "text": joined, "level": 0, "ref": None})

    figures = len(list(body.iter(W + "drawing"))) + len(list(body.iter(W + "pict")))
    for blip in body.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip"):
        rid = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
        if rid:
            images.add(rid)

    styled_headings = [p for p in paragraphs if p["is_heading"]]
    if len(styled_headings) < 3:
        for p in paragraphs:
            level = _fallback_heading(p)
            if level:
                p["level"] = level
                p["is_heading"] = True

    for p in paragraphs:
        if p["is_heading"] and not p["numbering"]:
            m = NUMBER_HEAD_RE.match(p["text"])
            if m:
                p["numbering"] = m.group(1)

    for block in blocks:
        if block["ref"] is not None:
            block["level"] = block["ref"]["level"] if block["ref"]["is_heading"] else 0

    headings = [p for p in paragraphs if p["is_heading"]]
    sections = _build_sections(blocks)

    core = _read_core_props(zf)
    header = _read_header_footer(zf, names, "word/header")
    footer = _read_header_footer(zf, names, "word/footer")

    font_chars = Counter()
    size_chars = Counter()
    for p in paragraphs:
        for k, v in p["fonts"].items():
            font_chars[k] += v
        for k, v in p["sizes"].items():
            size_chars[k] += v

    full_text = "\n".join(p["text"] for p in paragraphs if p["text"])
    if table_texts:
        full_text += "\n" + "\n".join(table_texts)

    max_level = max([p["level"] for p in headings], default=0)
    chapters = [p for p in headings if p["level"] == 1]
    if not chapters:
        chapters = [p for p in headings if p["numbering"] and "." not in p["numbering"]]

    return {
        "paragraphs": paragraphs,
        "headings": [{
            "text": p["text"],
            "level": p["level"],
            "index": p["index"],
            "numbering": p["numbering"],
        } for p in headings],
        "sections": sections,
        "tables": tables,
        "table_texts": table_texts,
        "figures": figures,
        "images": len(images),
        "full_text": full_text,
        "header_text": header["text"],
        "footer_text": footer["text"],
        "header_count": header["count"],
        "footer_count": footer["count"],
        "has_page_field": header["has_page_field"] or footer["has_page_field"],
        "core": core,
        "font_char_counts": dict(font_chars),
        "size_char_counts": dict(size_chars),
        "word_count": _count_words(full_text),
        "char_count": len(full_text),
        "paragraph_count": len([p for p in paragraphs if p["text"]]),
        "max_heading_level": max_level,
        "chapter_count": len(chapters),
    }
