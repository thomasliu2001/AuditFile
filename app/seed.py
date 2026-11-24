# -*- coding: utf-8 -*-
"""内置文档类型与默认稽核标准。"""
import json

from . import db
from .checks import PLACEHOLDER_PATTERNS

DOC_TYPES = [
    {
        "code": "srs",
        "name": "需求规格说明书",
        "description": "软件需求规格说明书，覆盖功能、性能与验收要求",
        "keywords": ["需求规格说明书", "需求规格", "需求说明书", "软件需求", "SRS"],
    },
    {
        "code": "hld",
        "name": "概要设计说明书",
        "description": "概要/总体设计说明书，覆盖架构、模块与接口设计",
        "keywords": ["概要设计说明书", "概要设计", "总体设计", "HLD"],
    },
    {
        "code": "lld",
        "name": "详细设计说明书",
        "description": "详细设计说明书，覆盖模块内部、数据结构与处理流程",
        "keywords": ["详细设计说明书", "详细设计", "LLD"],
    },
    {
        "code": "test_report",
        "name": "测试报告",
        "description": "测试总结报告，覆盖测试环境、用例、缺陷与结论",
        "keywords": ["测试报告", "测试总结报告", "测试报告书"],
    },
    {
        "code": "post_eval",
        "name": "后评估报告",
        "description": "项目后评估报告，覆盖过程、目标、效益与结论建议",
        "keywords": ["后评估报告", "后评价报告", "项目后评估", "后评估", "后评价"],
    },
]


def _rule(dimension, name, checker, params, severity, description="", sort_order=0):
    return {
        "dimension": dimension,
        "name": name,
        "checker": checker,
        "params": params,
        "severity": severity,
        "enabled": 1,
        "description": description,
        "sort_order": sort_order,
    }


def _structure_rules(sections, min_chapters=4, max_depth=4, min_tables=1, min_figures=0):
    rules = [
        _rule("structure", "必备章节齐全", "required_sections", {"sections": sections}, "high",
              "验收要求：关键章节不可缺失", 10),
        _rule("structure", "一级章节数量", "min_chapters", {"min": min_chapters}, "medium",
              "评估文档结构完整度", 20),
        _rule("structure", "标题层级上限", "max_heading_depth", {"max": max_depth}, "low",
              "避免章节层级过深影响可读性", 30),
        _rule("structure", "表格数量下限", "min_tables", {"min": min_tables}, "medium",
              "设计/测试/评估类文档需以表格承载结构化信息", 40),
    ]
    if min_figures:
        rules.append(_rule("structure", "插图数量下限", "min_figures", {"min": min_figures}, "low",
                           "架构图、流程图等图示要求", 50))
    return rules


def _content_rules(keywords, min_words, preferred, variants, forbidden=None, min_hits=None):
    rules = [
        _rule("content", "占位符与未完成标记", "placeholder_check",
              {"words": PLACEHOLDER_PATTERNS}, "high", "不可交付含 TODO/待补充 的文档", 10),
        _rule("content", "空章节检测", "empty_sections", {"ignore": ["附录", "参考资料"]}, "high",
              "空章节说明内容缺失", 20),
        _rule("content", "章节编号连续性", "numbering_continuity", {}, "medium",
              "编号跳号会造成条款无法追溯", 30),
        _rule("content", "正文规模下限", "min_word_count", {"min": min_words}, "medium",
              "评估内容充分性", 40),
        _rule("content", "必备内容关键词", "required_keywords",
              {"keywords": keywords, "min_hits": min_hits if min_hits is not None else len(keywords)},
              "high", "验收关注的核心内容必须覆盖", 50),
        _rule("content", "术语一致性", "term_consistency",
              {"preferred": preferred, "variants": variants}, "low",
              "同一概念需使用统一表述", 60),
    ]
    if forbidden:
        rules.insert(0, _rule("content", "禁用词/模糊表述", "forbidden_words", {"words": forbidden},
                              "medium", "验收文档不得使用模糊、不可验证的表述", 5))
    return rules


def _metadata_rules(cover_keywords):
    return [
        _rule("metadata", "封面标题", "cover_title", {"keywords": cover_keywords, "within": 20}, "high",
              "封面须体现文档类型", 10),
        _rule("metadata", "文档编号", "doc_number",
              {"regex": "[A-Z]{2,6}[-_ ]?\\d{2,6}", "within": 40}, "medium",
              "文档编号用于归档追溯", 20),
        _rule("metadata", "版本修订记录", "version_record",
              {"keywords": ["版本", "修订", "版本历史"], "version_regex": "[Vv]?\\d+\\.\\d+"}, "high",
              "版本记录是配置管理要求", 30),
        _rule("metadata", "审批签署要素", "approval_signature",
              {"roles": ["编制", "审核", "批准"]}, "high",
              "缺少签署无法确认文档生效", 40),
        _rule("metadata", "日期标注", "date_presence",
              {"regex": "\\d{4}\\s*[年\\-/\\.]\\s*\\d{1,2}", "within": 40}, "low",
              "日期需可识别", 50),
        _rule("metadata", "文档属性完整", "core_properties", {"fields": ["title", "author"]}, "low",
              "Word 文档属性用于检索与归档", 60),
        _rule("metadata", "密级标注", "confidentiality",
              {"keywords": ["密级", "保密", "内部公开"]}, "medium",
              "验收材料需标注密级", 70),
    ]


def _format_rules():
    return [
        _rule("format", "正文字体", "font_name",
              {"expected": ["宋体", "仿宋", "仿宋_GB2312"], "min_ratio": 0.5}, "medium",
              "按字号字符占比统计（阈值 50%）", 10),
        _rule("format", "正文字号", "font_size",
              {"expected_pt": 12, "tolerance_pt": 0.5, "min_ratio": 0.5}, "medium",
              "正文小四号（12pt）为常见验收要求", 20),
        _rule("format", "页眉页脚", "header_footer",
              {"require_header": True, "require_footer": True}, "low",
              "页眉页脚承载项目标识", 30),
        _rule("format", "页码设置", "page_number", {}, "low",
              "正式文档需具备自动页码", 40),
    ]


DEFAULT_RULES = {
    "srs": (
        _structure_rules(["引言", "任务概述", "功能需求", "性能需求", "运行环境", "验收标准"],
                         min_chapters=4, max_depth=4, min_tables=1)
        + _content_rules(["功能需求", "性能", "安全"], 2000, "系统", ["平台", "软件产品"],
                         forbidden=["大概", "也许", "可能"])
        + _metadata_rules(["需求规格说明书", "需求规格"])
        + _format_rules()
    ),
    "hld": (
        _structure_rules(["引言", "总体设计", "系统架构", "模块设计", "接口设计", "数据库设计"],
                         min_chapters=4, max_depth=4, min_tables=2, min_figures=1)
        + _content_rules(["架构", "模块", "接口"], 1500, "系统", ["平台"])
        + _metadata_rules(["概要设计说明书", "概要设计", "总体设计"])
        + _format_rules()
    ),
    "lld": (
        _structure_rules(["引言", "模块设计", "接口设计", "数据结构", "处理流程", "错误处理"],
                         min_chapters=4, max_depth=4, min_tables=2, min_figures=1)
        + _content_rules(["接口", "数据结构", "流程"], 1500, "系统", ["平台"])
        + _metadata_rules(["详细设计说明书", "详细设计"])
        + _format_rules()
    ),
    "test_report": (
        _structure_rules(["引言", "测试环境", "测试用例", "测试执行", "缺陷", "测试结论"],
                         min_chapters=4, max_depth=3, min_tables=3)
        + _content_rules(["测试用例", "缺陷", "覆盖率"], 1200, "测试用例", ["测试案例", "测试实例"])
        + _metadata_rules(["测试报告", "测试总结"])
        + _format_rules()
    ),
    "post_eval": (
        _structure_rules(["引言", "项目概况", "过程评估", "目标评估", "效益评估", "评估结论", "建议"],
                         min_chapters=4, max_depth=4, min_tables=2)
        + _content_rules(["效益", "结论", "建议"], 1200, "评估", ["评价"],
                         forbidden=["大概", "也许", "可能"])
        + _metadata_rules(["后评估报告", "后评估", "后评价"])
        + _format_rules()
    ),
}


def _insert_rules(doc_type, rules):
    rows = [(
        doc_type, r["dimension"], r["name"], r["checker"], json.dumps(r["params"], ensure_ascii=False),
        r["severity"], r["enabled"], r["description"], r["sort_order"], db.now_str(),
    ) for r in rules]
    db.execute_many(
        "INSERT INTO rules (doc_type, dimension, name, checker, params, severity, enabled, description,"
        " sort_order, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)", rows)


def _publish(doc_type, note):
    rows = db.query("SELECT * FROM rules WHERE doc_type=? ORDER BY dimension, sort_order, id", (doc_type,))
    snapshot = []
    for r in rows:
        item = dict(r)
        try:
            item["params"] = json.loads(item["params"] or "{}")
        except ValueError:
            item["params"] = {}
        snapshot.append(item)
    last = db.query_one("SELECT MAX(version_no) AS v FROM standard_versions WHERE doc_type=?", (doc_type,))
    version_no = (last["v"] or 0) + 1 if last else 1
    db.execute(
        "INSERT INTO standard_versions (doc_type, version_no, note, snapshot, rule_count, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (doc_type, version_no, note, json.dumps(snapshot, ensure_ascii=False), len(snapshot), db.now_str()),
    )


def ensure_seed():
    """幂等写入内置文档类型、默认规则与初始标准版本。"""
    existing = {row["code"] for row in db.query("SELECT code FROM doc_types")}
    for idx, dt in enumerate(DOC_TYPES):
        if dt["code"] in existing:
            continue
        db.execute(
            "INSERT INTO doc_types (code, name, description, filename_keywords, sort_order)"
            " VALUES (?,?,?,?,?)",
            (dt["code"], dt["name"], dt["description"],
             json.dumps(dt["keywords"], ensure_ascii=False), idx),
        )
        _insert_rules(dt["code"], DEFAULT_RULES[dt["code"]])
        _publish(dt["code"], "系统内置默认标准")


def reset_rules(doc_type):
    db.execute("DELETE FROM rules WHERE doc_type=?", (doc_type,))
    _insert_rules(doc_type, DEFAULT_RULES[doc_type])
    _publish(doc_type, "恢复默认标准")
