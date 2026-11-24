# -*- coding: utf-8 -*-
"""四维稽核规则引擎。每个检查器返回 pass / fail / skip 三态结果。"""
import re

DIMENSIONS = [
    {"key": "structure", "name": "结构完整性"},
    {"key": "content", "name": "内容规范"},
    {"key": "metadata", "name": "文档元信息"},
    {"key": "format", "name": "格式合规"},
]

DIMENSION_NAMES = {d["key"]: d["name"] for d in DIMENSIONS}
PLACEHOLDER_PATTERNS = ["TODO", "TBD", "FIXME", "XXX", "待补充", "待完善", "待确认", "待定", "此处填写", "【填写】"]
NORM_RE = re.compile(r"[\s:：、，,。.．\-—_（）()【】\[\]]+")


def _norm(text):
    return NORM_RE.sub("", text or "").lower()


def _pass(message, evidence="", location=""):
    return {"status": "pass", "message": message, "evidence": evidence, "location": location}


def _fail(message, evidence="", location=""):
    return {"status": "fail", "message": message, "evidence": evidence, "location": location}


def _skip(message):
    return {"status": "skip", "message": message, "evidence": "", "location": ""}


def _context(text, keyword, width=24):
    lower = text.lower()
    pos = lower.find(keyword.lower())
    if pos < 0:
        return ""
    start = max(0, pos - width)
    end = min(len(text), pos + len(keyword) + width)
    return text[start:end].replace("\n", " ")


def _format_ratio(counts, hits, total):
    if not total:
        return "无可统计字符"
    parts = sorted(counts.items(), key=lambda kv: -kv[1])[:4]
    detail = "、".join("%s %.0f%%" % (k, v * 100.0 / total) for k, v in parts)
    matched = "、".join("%s %.0f%%" % (k, counts.get(k, 0) * 100.0 / total) for k in hits)
    return "命中：%s；实际分布：%s" % (matched, detail)


# ---------------------------------------------------------------- 结构完整性

def check_required_sections(ctx, p):
    sections = p.get("sections") or []
    if not sections:
        return _skip("规则未配置必备章节，跳过")
    doc = ctx["doc"]
    heads = doc["headings"]
    pool = [h["text"] for h in heads] if heads else [x["text"] for x in doc["paragraphs"] if x["text"]]
    pool_norm = [_norm(x) for x in pool]
    found, missing = [], []
    for s in sections:
        key = _norm(s)
        if any(key and key in item for item in pool_norm):
            found.append(s)
        else:
            missing.append(s)
    if missing:
        return _fail(
            "缺少 %d 个必备章节：%s" % (len(missing), "、".join(missing)),
            "已命中：%s" % ("、".join(found) if found else "无"),
            "章节结构",
        )
    return _pass("必备章节齐全（%d 项）" % len(sections), "、".join(found), "章节结构")


def check_min_chapters(ctx, p):
    minimum = int(p.get("min", 4))
    count = ctx["doc"]["chapter_count"]
    if count >= minimum:
        return _pass("一级章节 %d 个（要求 ≥ %d）" % (count, minimum), "", "章节结构")
    return _fail("一级章节仅 %d 个，少于要求 %d 个" % (count, minimum), "章节数统计", "章节结构")


def check_max_heading_depth(ctx, p):
    maximum = int(p.get("max", 4))
    level = ctx["doc"]["max_heading_level"]
    if not level:
        return _skip("未识别到标题层级")
    if level <= maximum:
        return _pass("最大标题层级为 %d（要求 ≤ %d）" % (level, maximum), "", "标题层级")
    return _fail("标题层级过深：最大 %d 级（要求 ≤ %d 级）" % (level, maximum), "", "标题层级")


def check_min_tables(ctx, p):
    minimum = int(p.get("min", 1))
    count = ctx["doc"]["tables"]
    if count >= minimum:
        return _pass("表格数量 %d（要求 ≥ %d）" % (count, minimum), "", "表格")
    return _fail("表格数量 %d，少于要求 %d" % (count, minimum), "", "表格")


def check_min_figures(ctx, p):
    minimum = int(p.get("min", 1))
    count = ctx["doc"]["figures"]
    if count >= minimum:
        return _pass("插图数量 %d（要求 ≥ %d）" % (count, minimum), "", "插图")
    return _fail("插图数量 %d，少于要求 %d" % (count, minimum), "", "插图")


def check_required_appendix(ctx, p):
    keywords = p.get("keywords") or ["附录"]
    doc = ctx["doc"]
    hits = [k for k in keywords if _norm(k) in _norm(doc["full_text"])]
    if hits:
        return _pass("存在附录内容：%s" % "、".join(hits), "", "附录")
    return _fail("未发现附录内容（关键词：%s）" % "、".join(keywords), "", "附录")


# ---------------------------------------------------------------- 内容规范

def check_forbidden_words(ctx, p):
    words = [w for w in (p.get("words") or []) if w]
    if not words:
        return _skip("规则未配置禁用词，跳过")
    text = ctx["doc"]["full_text"]
    hit_details = []
    total = 0
    for w in words:
        count = text.lower().count(w.lower())
        if count:
            total += count
            hit_details.append("「%s」%d 次：…%s…" % (w, count, _context(text, w)))
    if total:
        return _fail("发现 %d 处不规范/禁用表述" % total, "\n".join(hit_details[:6]), "正文")
    return _pass("未命中禁用词（%d 个词）" % len(words), "", "正文")


def check_placeholder(ctx, p):
    words = p.get("words") or PLACEHOLDER_PATTERNS
    text = ctx["doc"]["full_text"]
    hits = []
    total = 0
    for w in words:
        if w.upper() in ("TODO", "TBD", "FIXME", "XXX"):
            count = len(re.findall(re.escape(w), text, re.IGNORECASE))
        else:
            count = text.count(w)
        if count:
            total += count
            hits.append("「%s」%d 次：…%s…" % (w, count, _context(text, w)))
    if total:
        return _fail("存在 %d 处占位符/未完成标记" % total, "\n".join(hits[:6]), "正文")
    return _pass("未发现占位符或未完成标记", "", "正文")


def check_empty_sections(ctx, p):
    ignore = [_norm(x) for x in (p.get("ignore") or [])]
    empties = []
    for s in ctx["doc"]["sections"]:
        if s["children"]:
            continue
        if not _norm(s["body"]):
            if any(k and k in _norm(s["title"]) for k in ignore):
                continue
            empties.append(s["title"])
    if empties:
        return _fail(
            "存在 %d 个空章节：%s" % (len(empties), "、".join(empties[:8])),
            "章节标题已列出但正文为空", "章节内容",
        )
    return _pass("所有章节均有正文内容", "", "章节内容")


def check_numbering(ctx, p):
    heads = [h for h in ctx["doc"]["headings"] if h.get("numbering")]
    if not heads:
        return _skip("未识别到章节编号，无法校验连续性")
    last = {}
    issues = []
    for h in heads:
        try:
            parts = [int(x) for x in h["numbering"].split(".")]
        except ValueError:
            continue
        prefix = tuple(parts[:-1])
        expected = last.get(prefix, 0) + 1
        if parts[-1] != expected:
            issues.append("「%s」编号应为 %s，实际为 %s" % (
                h["text"][:30],
                ".".join(str(x) for x in list(prefix) + [expected]),
                h["numbering"],
            ))
        last[prefix] = parts[-1]
    if issues:
        return _fail("章节编号不连续，共 %d 处" % len(issues), "\n".join(issues[:6]), "章节编号")
    return _pass("章节编号连续（校验 %d 个标题）" % len(heads), "", "章节编号")


def check_min_words(ctx, p):
    minimum = int(p.get("min", 1000))
    count = ctx["doc"]["word_count"]
    if count >= minimum:
        return _pass("正文规模 %d 字（要求 ≥ %d）" % (count, minimum), "", "正文")
    return _fail("正文规模仅 %d 字，少于要求 %d 字" % (count, minimum), "", "正文")


def check_required_keywords(ctx, p):
    keywords = [k for k in (p.get("keywords") or []) if k]
    if not keywords:
        return _skip("规则未配置必备关键词，跳过")
    min_hits = int(p.get("min_hits") or len(keywords))
    text = ctx["doc"]["full_text"]
    hits = [k for k in keywords if k in text]
    missing = [k for k in keywords if k not in text]
    if len(hits) >= min_hits:
        return _pass("命中必备关键词 %d/%d 个：%s" % (len(hits), len(keywords), "、".join(hits)),
                     "" if not missing else "未命中：%s" % "、".join(missing), "正文")
    return _fail("必备关键词命中不足（%d/%d，要求 ≥ %d）：缺少 %s" % (
        len(hits), len(keywords), min_hits, "、".join(missing)), "", "正文")


def check_term_consistency(ctx, p):
    preferred = (p.get("preferred") or "").strip()
    variants = [v for v in (p.get("variants") or []) if v]
    if not preferred or not variants:
        return _skip("规则未配置统一术语或变体，跳过")
    text = ctx["doc"]["full_text"]
    base = text.count(preferred)
    variant_hits = [(v, text.count(v)) for v in variants if text.count(v)]
    if variant_hits:
        detail = "建议统一为「%s」（当前 %d 次）；" % (preferred, base)
        detail += "、".join("「%s」%d 次" % (v, c) for v, c in variant_hits)
        return _fail("术语表述不统一：%s" % detail, "存在同义变体表述", "术语")
    if not base:
        return _skip("正文未出现术语「%s」，无法判断一致性" % preferred)
    return _pass("术语统一为「%s」（%d 次），未见变体" % (preferred, base), "", "术语")


# ---------------------------------------------------------------- 文档元信息

def _front_text(doc, within=40):
    return "\n".join(x["text"] for x in doc["paragraphs"][:within] if x["text"])


def check_cover_title(ctx, p):
    keywords = [k for k in (p.get("keywords") or []) if k]
    if not keywords:
        keywords = [ctx.get("doc_type_name") or ""]
    within = int(p.get("within", 20))
    front = _front_text(ctx["doc"], within)
    hits = [k for k in keywords if k and k in front]
    if hits:
        return _pass("封面标题包含文档类型标识：%s" % "、".join(hits), "", "封面")
    return _fail("文档前 %d 段未出现标题关键词（%s）" % (within, "、".join(keywords)), "", "封面")


def check_doc_number(ctx, p):
    pattern = p.get("regex") or r"[A-Z]{2,6}[-_ ]?\d{2,6}"
    within = int(p.get("within", 40))
    front = _front_text(ctx["doc"], within)
    m = re.search(pattern, front)
    if m:
        return _pass("识别到文档编号：%s" % m.group(0), "", "文档编号")
    return _fail("前 %d 段未识别到符合规则的文档编号（正则：%s）" % (within, pattern), "", "文档编号")


def check_version_record(ctx, p):
    keywords = [k for k in (p.get("keywords") or ["版本", "修订", "版本历史"]) if k]
    version_regex = p.get("version_regex") or r"[Vv]?\d+\.\d+"
    text = ctx["doc"]["full_text"]
    hit_keywords = [k for k in keywords if k in text]
    version = re.search(version_regex, text)
    if hit_keywords and version:
        return _pass("存在版本修订记录（%s，版本号 %s）" % ("、".join(hit_keywords), version.group(0)), "", "版本记录")
    missing = []
    if not hit_keywords:
        missing.append("版本/修订说明")
    if not version:
        missing.append("版本号")
    return _fail("缺少%s，无法追溯文档版本" % "、".join(missing), "关键词：%s" % "、".join(keywords), "版本记录")


def check_approval(ctx, p):
    roles = [r for r in (p.get("roles") or ["编制", "审核", "批准"]) if r]
    text = ctx["doc"]["full_text"]
    missing = [r for r in roles if r not in text]
    if missing:
        return _fail("缺少签署角色：%s" % "、".join(missing), "已具备：%s" % "、".join(
            [r for r in roles if r not in missing]), "签署栏")
    return _pass("编制/审核/批准签署要素齐全", "、".join(roles), "签署栏")


def check_date_presence(ctx, p):
    pattern = p.get("regex") or r"\d{4}\s*[年\-/\.]\s*\d{1,2}"
    within = int(p.get("within", 40))
    front = _front_text(ctx["doc"], within)
    m = re.search(pattern, front) or re.search(pattern, ctx["doc"]["full_text"])
    if m:
        return _pass("存在规范日期：%s" % m.group(0), "", "日期")
    return _fail("未识别到符合规则的日期（正则：%s）" % pattern, "", "日期")


def check_core_properties(ctx, p):
    fields = p.get("fields") or ["title", "author"]
    core = ctx["doc"]["core"]
    missing = [f for f in fields if not (core.get(f) or "").strip()]
    if missing:
        return _fail("文档属性缺失：%s" % "、".join(missing), "可在 Word 文件-信息中补全", "文档属性")
    detail = "、".join("%s=%s" % (f, core.get(f)) for f in fields)
    return _pass("文档属性完整", detail, "文档属性")


def check_confidentiality(ctx, p):
    keywords = [k for k in (p.get("keywords") or ["密级", "保密", "内部公开"]) if k]
    text = ctx["doc"]["full_text"]
    hits = [k for k in keywords if k in text]
    if hits:
        return _pass("标注了密级/保密要求：%s" % "、".join(hits), "", "密级标注")
    return _fail("未标注密级信息（关键词：%s）" % "、".join(keywords), "", "密级标注")


# ---------------------------------------------------------------- 格式合规

def check_font_name(ctx, p):
    expected = [x for x in (p.get("expected") or []) if x]
    min_ratio = float(p.get("min_ratio", 0.5))
    counts = ctx["doc"]["font_char_counts"]
    if not expected:
        return _skip("规则未配置期望字体，跳过")
    total = sum(counts.values())
    if not total:
        return _skip("文档未显式设置字体（使用默认样式），无法判定")
    hits = {k: v for k, v in counts.items() if any(e in k for e in expected)}
    ratio = sum(hits.values()) / float(total)
    detail = _format_ratio(counts, list(hits.keys()), total)
    if ratio >= min_ratio:
        return _pass("正文字体合规率 %.0f%%（要求 ≥ %.0f%%）" % (ratio * 100, min_ratio * 100), detail, "字体")
    return _fail("正文字体合规率仅 %.0f%%（要求 ≥ %.0f%%，期望：%s）" % (
        ratio * 100, min_ratio * 100, "、".join(expected)), detail, "字体")


def check_font_size(ctx, p):
    expected_pt = float(p.get("expected_pt", 12))
    tolerance = float(p.get("tolerance_pt", 0.5))
    min_ratio = float(p.get("min_ratio", 0.5))
    counts = ctx["doc"]["size_char_counts"]
    if not counts:
        return _skip("文档未显式设置字号，无法判定")
    total = sum(counts.values())
    hits = {}
    for k, v in counts.items():
        try:
            if abs(float(k) - expected_pt) <= tolerance:
                hits[k] = v
        except ValueError:
            continue
    ratio = sum(hits.values()) / float(total)
    detail = _format_ratio(counts, list(hits.keys()), total)
    if ratio >= min_ratio:
        return _pass("正文字号合规率 %.0f%%（期望 %.1fpt）" % (ratio * 100, expected_pt), detail, "字号")
    return _fail("正文字号合规率仅 %.0f%%（期望 %.1fpt ± %.1f）" % (
        ratio * 100, expected_pt, tolerance), detail, "字号")


def check_header_footer(ctx, p):
    doc = ctx["doc"]
    problems = []
    if p.get("require_header", True) and not doc["header_count"]:
        problems.append("缺少页眉")
    if p.get("require_footer", True) and not doc["footer_count"]:
        problems.append("缺少页脚")
    if problems:
        return _fail("、".join(problems), "页眉页脚用于承载项目标识与页码", "页眉页脚")
    return _pass("页眉页脚齐全", "页眉 %d 个 / 页脚 %d 个" % (doc["header_count"], doc["footer_count"]), "页眉页脚")


def check_page_number(ctx, p):
    doc = ctx["doc"]
    pattern = p.get("regex") or r"第\s*\d+\s*页|\d+\s*/\s*\d+|Page\s*\d+"
    if doc["has_page_field"]:
        return _pass("页脚包含自动页码域", "", "页码")
    if re.search(pattern, doc["footer_text"] + " " + doc["header_text"]):
        return _pass("页眉/页脚包含页码", "", "页码")
    return _fail("未检测到页码（无 PAGE 域，也无“第 X 页”文本）", "", "页码")


# ---------------------------------------------------------------- 注册表

CHECKS = {
    "required_sections": {
        "label": "必备章节齐全", "dimension": "structure",
        "description": "文档标题/段落中必须出现全部指定章节关键词",
        "params_example": {"sections": ["引言", "参考文档"]},
        "func": check_required_sections,
    },
    "min_chapters": {
        "label": "一级章节数量下限", "dimension": "structure",
        "description": "一级标题数量不得少于阈值",
        "params_example": {"min": 4},
        "func": check_min_chapters,
    },
    "max_heading_depth": {
        "label": "标题层级上限", "dimension": "structure",
        "description": "标题层级不得超过阈值，避免结构过深",
        "params_example": {"max": 4},
        "func": check_max_heading_depth,
    },
    "min_tables": {
        "label": "表格数量下限", "dimension": "structure",
        "description": "文档表格数量不得少于阈值",
        "params_example": {"min": 1},
        "func": check_min_tables,
    },
    "min_figures": {
        "label": "插图数量下限", "dimension": "structure",
        "description": "文档插图/图示数量不得少于阈值",
        "params_example": {"min": 1},
        "func": check_min_figures,
    },
    "required_appendix": {
        "label": "附录存在性", "dimension": "structure",
        "description": "文档需包含附录类内容",
        "params_example": {"keywords": ["附录"]},
        "func": check_required_appendix,
    },
    "forbidden_words": {
        "label": "禁用词/不规范表述", "dimension": "content",
        "description": "正文不得出现指定的禁用词或模糊表述",
        "params_example": {"words": ["大概", "也许", "待补充"]},
        "func": check_forbidden_words,
    },
    "placeholder_check": {
        "label": "占位符与未完成标记", "dimension": "content",
        "description": "检测 TODO/TBD/XXX/待补充 等占位内容",
        "params_example": {"words": PLACEHOLDER_PATTERNS},
        "func": check_placeholder,
    },
    "empty_sections": {
        "label": "空章节检测", "dimension": "content",
        "description": "章节标题下必须有正文内容",
        "params_example": {"ignore": ["附录"]},
        "func": check_empty_sections,
    },
    "numbering_continuity": {
        "label": "章节编号连续性", "dimension": "content",
        "description": "章节编号需按同级顺序连续递增",
        "params_example": {},
        "func": check_numbering,
    },
    "min_word_count": {
        "label": "正文规模下限", "dimension": "content",
        "description": "正文中文字符与词数不得少于阈值",
        "params_example": {"min": 1000},
        "func": check_min_words,
    },
    "required_keywords": {
        "label": "必备内容关键词", "dimension": "content",
        "description": "文档必须覆盖指定关键内容，可设置最少命中数",
        "params_example": {"keywords": ["功能需求", "性能"], "min_hits": 2},
        "func": check_required_keywords,
    },
    "term_consistency": {
        "label": "术语一致性", "dimension": "content",
        "description": "统一术语表述，禁止同义变体混用",
        "params_example": {"preferred": "系统", "variants": ["平台", "软件产品"]},
        "func": check_term_consistency,
    },
    "cover_title": {
        "label": "封面标题", "dimension": "metadata",
        "description": "文档前若干段必须出现文档类型标题",
        "params_example": {"keywords": ["需求规格说明书"], "within": 20},
        "func": check_cover_title,
    },
    "doc_number": {
        "label": "文档编号", "dimension": "metadata",
        "description": "封面区域需包含符合正则的文档编号",
        "params_example": {"regex": "[A-Z]{2,6}[-_ ]?\\d{2,6}", "within": 40},
        "func": check_doc_number,
    },
    "version_record": {
        "label": "版本修订记录", "dimension": "metadata",
        "description": "必须具备版本说明与版本号，便于追溯",
        "params_example": {"keywords": ["版本", "修订"], "version_regex": "[Vv]?\\d+\\.\\d+"},
        "func": check_version_record,
    },
    "approval_signature": {
        "label": "审批签署要素", "dimension": "metadata",
        "description": "文档需包含编制/审核/批准等签署角色",
        "params_example": {"roles": ["编制", "审核", "批准"]},
        "func": check_approval,
    },
    "date_presence": {
        "label": "日期标注", "dimension": "metadata",
        "description": "文档需包含规范格式日期",
        "params_example": {"regex": "\\d{4}\\s*[年\\-/\\.]\\s*\\d{1,2}", "within": 40},
        "func": check_date_presence,
    },
    "core_properties": {
        "label": "文档属性完整", "dimension": "metadata",
        "description": "docx 核心属性（标题/作者等）不得为空",
        "params_example": {"fields": ["title", "author"]},
        "func": check_core_properties,
    },
    "confidentiality": {
        "label": "密级标注", "dimension": "metadata",
        "description": "文档需标注密级或保密要求",
        "params_example": {"keywords": ["密级", "保密"]},
        "func": check_confidentiality,
    },
    "font_name": {
        "label": "正文字体", "dimension": "format",
        "description": "按字符占比统计正文字体是否合规",
        "params_example": {"expected": ["宋体", "仿宋"], "min_ratio": 0.5},
        "func": check_font_name,
    },
    "font_size": {
        "label": "正文字号", "dimension": "format",
        "description": "按字符占比统计正文字号是否合规",
        "params_example": {"expected_pt": 12, "tolerance_pt": 0.5, "min_ratio": 0.5},
        "func": check_font_size,
    },
    "header_footer": {
        "label": "页眉页脚", "dimension": "format",
        "description": "检查是否设置页眉与页脚",
        "params_example": {"require_header": True, "require_footer": True},
        "func": check_header_footer,
    },
    "page_number": {
        "label": "页码设置", "dimension": "format",
        "description": "页脚需包含自动页码域或页码文本",
        "params_example": {},
        "func": check_page_number,
    },
}


def checkers_meta():
    return [{
        "key": key,
        "label": meta["label"],
        "dimension": meta["dimension"],
        "dimension_name": DIMENSION_NAMES[meta["dimension"]],
        "description": meta["description"],
        "params_example": meta["params_example"],
    } for key, meta in CHECKS.items()]


def apply_rule(rule, ctx):
    meta = CHECKS.get(rule.get("checker"))
    if not meta:
        return {"status": "skip", "message": "未知检查器：%s" % rule.get("checker"), "evidence": "", "location": ""}
    try:
        return meta["func"](ctx, rule.get("params") or {})
    except Exception as exc:  # 单条规则失败不影响整份文档
        return {"status": "skip", "message": "规则执行异常：%s" % exc, "evidence": "", "location": ""}
