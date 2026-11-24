# -*- coding: utf-8 -*-
"""稽核执行：单文档稽核、项目目录批量稽核、评分与留痕。"""
import hashlib
import json
import os
import time

from . import db
from .checks import DIMENSIONS, apply_rule
from .parser import parse_docx

SEVERITY_WEIGHT = {"high": 5, "medium": 3, "low": 1}
DIM_ORDER = {d["key"]: i for i, d in enumerate(DIMENSIONS)}


def grade_of(score):
    if score >= 90:
        return "优秀"
    if score >= 75:
        return "良好"
    if score >= 60:
        return "合格"
    return "不合格"


def _parse_params(value):
    try:
        data = json.loads(value or "{}")
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _doc_type_name(code):
    row = db.query_one("SELECT name FROM doc_types WHERE code=?", (code,))
    return row["name"] if row else code


def active_rules(doc_type):
    rows = db.query(
        "SELECT * FROM rules WHERE doc_type=? AND enabled=1 ORDER BY sort_order, id", (doc_type,))
    for r in rows:
        r["params"] = _parse_params(r["params"])
    return rows


def latest_version(doc_type):
    return db.query_one(
        "SELECT id, version_no, note, created_at FROM standard_versions"
        " WHERE doc_type=? ORDER BY version_no DESC LIMIT 1", (doc_type,))


def run_audit(doc_type, file_name, data, project_name="", batch_id=None, file_path="", persist=True):
    started = time.time()
    version = latest_version(doc_type)
    rules = active_rules(doc_type)
    snapshot = [{
        "id": r["id"], "dimension": r["dimension"], "name": r["name"], "checker": r["checker"],
        "params": r["params"], "severity": r["severity"],
    } for r in rules]

    findings = []
    status = "done"
    error = ""
    score = 0.0
    passed = failed = skipped = 0
    doc_meta = {}

    try:
        doc = parse_docx(data)
        doc_meta = {
            "word_count": doc["word_count"],
            "paragraph_count": doc["paragraph_count"],
            "tables": doc["tables"],
            "figures": doc["figures"],
            "chapter_count": doc["chapter_count"],
            "max_heading_level": doc["max_heading_level"],
        }
        ctx = {"doc": doc, "file_name": file_name, "doc_type": doc_type,
               "doc_type_name": _doc_type_name(doc_type)}
        for r in rules:
            res = apply_rule(r, ctx)
            if res["status"] == "pass":
                passed += 1
            elif res["status"] == "fail":
                failed += 1
            else:
                skipped += 1
            findings.append({
                "rule_id": r["id"],
                "dimension": r["dimension"],
                "rule_name": r["name"],
                "severity": r["severity"],
                "status": res["status"],
                "message": res["message"],
                "evidence": res["evidence"],
                "location": res["location"],
                "sort_order": r["sort_order"],
            })
        total_weight = sum(SEVERITY_WEIGHT.get(f["severity"], 1)
                           for f in findings if f["status"] in ("pass", "fail"))
        pass_weight = sum(SEVERITY_WEIGHT.get(f["severity"], 1)
                          for f in findings if f["status"] == "pass")
        score = round(pass_weight * 100.0 / total_weight, 1) if total_weight else 0.0
    except Exception as exc:
        status = "error"
        error = str(exc)
        score = 0.0

    duration = int((time.time() - started) * 1000)
    if not persist:
        return {
            "status": status, "error": error, "score": score, "grade": grade_of(score) if status == "done" else "无法稽核",
            "total_rules": len(rules), "passed_rules": passed, "failed_rules": failed,
            "skipped_rules": skipped, "findings": findings, "doc_meta": doc_meta,
            "duration_ms": duration, "file_name": file_name, "doc_type": doc_type,
        }

    run_id = db.execute(
        "INSERT INTO audit_runs (batch_id, project_name, doc_type, file_name, file_path, file_hash,"
        " file_size, standard_version_id, standard_snapshot, doc_meta, total_rules, passed_rules,"
        " failed_rules, skipped_rules, score, grade, status, error, created_at, duration_ms)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (batch_id, project_name, doc_type, file_name, file_path,
         hashlib.sha256(data).hexdigest(), len(data),
         version["id"] if version else None, json.dumps(snapshot, ensure_ascii=False),
         json.dumps(doc_meta, ensure_ascii=False), len(rules), passed, failed, skipped, score,
         grade_of(score) if status == "done" else "无法稽核", status, error, db.now_str(), duration),
    )
    if findings:
        rows = []
        for f in findings:
            rows.append((run_id, f["rule_id"], f["dimension"], f["rule_name"], f["severity"],
                         f["status"], f["message"], f["evidence"], f["location"], f["sort_order"]))
        db.execute_many(
            "INSERT INTO audit_findings (run_id, rule_id, dimension, rule_name, severity, status,"
            " message, evidence, location, sort_order) VALUES (?,?,?,?,?,?,?,?,?,?)", rows)

    return {
        "id": run_id, "status": status, "error": error, "score": score,
        "grade": grade_of(score) if status == "done" else "无法稽核",
        "total_rules": len(rules), "passed_rules": passed, "failed_rules": failed,
        "skipped_rules": skipped, "findings": findings, "doc_meta": doc_meta,
        "duration_ms": duration, "file_name": file_name, "doc_type": doc_type,
    }


def get_run(run_id):
    run = db.query_one(
        "SELECT r.*, v.version_no AS standard_version_no FROM audit_runs r"
        " LEFT JOIN standard_versions v ON v.id = r.standard_version_id WHERE r.id=?", (run_id,))
    if not run:
        return None
    run["doc_type_name"] = _doc_type_name(run["doc_type"])
    try:
        run["standard_snapshot"] = json.loads(run["standard_snapshot"] or "[]")
    except ValueError:
        run["standard_snapshot"] = []
    try:
        run["doc_meta"] = json.loads(run["doc_meta"] or "{}")
    except ValueError:
        run["doc_meta"] = {}
    findings = db.query("SELECT * FROM audit_findings WHERE run_id=?", (run_id,))
    findings.sort(key=lambda f: (DIM_ORDER.get(f["dimension"], 99), f["sort_order"], f["id"]))
    run["findings"] = findings
    return run


def doc_types():
    rows = db.query("SELECT * FROM doc_types ORDER BY sort_order, code")
    for r in rows:
        try:
            r["filename_keywords"] = json.loads(r["filename_keywords"] or "[]")
        except ValueError:
            r["filename_keywords"] = []
        count = db.query_one("SELECT COUNT(*) AS c FROM rules WHERE doc_type=?", (r["code"],))
        r["rule_count"] = count["c"] if count else 0
    return rows


def detect_doc_type(file_name, types=None):
    types = types or doc_types()
    base = os.path.basename(file_name).lower()
    best = None
    best_len = 0
    for t in types:
        for kw in t["filename_keywords"]:
            if kw and kw.lower() in base and len(kw) > best_len:
                best = t
                best_len = len(kw)
    return best


def publish_version(doc_type, note=""):
    rows = active_rules(doc_type)
    for r in rows:
        r.pop("updated_at", None)
    last = db.query_one("SELECT MAX(version_no) AS v FROM standard_versions WHERE doc_type=?", (doc_type,))
    version_no = (last["v"] or 0) + 1 if last else 1
    db.execute(
        "INSERT INTO standard_versions (doc_type, version_no, note, snapshot, rule_count, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (doc_type, version_no, note or "手工发布", json.dumps(rows, ensure_ascii=False),
         len(rows), db.now_str()),
    )
    return version_no


def list_versions(doc_type):
    rows = db.query(
        "SELECT id, doc_type, version_no, note, rule_count, created_at FROM standard_versions"
        " WHERE doc_type=? ORDER BY version_no DESC", (doc_type,))
    return rows


def _iter_docx_files(dir_path, max_depth=5, limit=300):
    found = []
    base_depth = dir_path.rstrip(os.sep).count(os.sep)
    for root, dirs, names in os.walk(dir_path):
        depth = root.count(os.sep) - base_depth
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in (
            "node_modules", "__pycache__", "venv", "env", ".git")]
        if depth >= max_depth:
            dirs[:] = []
        for name in sorted(names):
            if name.startswith("~$"):
                continue
            if name.lower().endswith(".docx"):
                found.append(os.path.join(root, name))
                if len(found) >= limit:
                    return found
    return found


def scan_directory(dir_path, project_name=""):
    if not os.path.isdir(dir_path):
        raise ValueError("目录不存在或不可访问：%s" % dir_path)
    types = doc_types()
    files = _iter_docx_files(dir_path)
    matched = []
    unmatched = []
    for path in files:
        t = detect_doc_type(path, types)
        size = os.path.getsize(path)
        if t:
            matched.append({
                "file_path": path,
                "file_name": os.path.basename(path),
                "doc_type": t["code"],
                "doc_type_name": t["name"],
                "file_size": size,
            })
        else:
            unmatched.append({"file_path": path, "file_name": os.path.basename(path), "file_size": size})
    return {
        "project_name": project_name or os.path.basename(os.path.abspath(dir_path)),
        "source_dir": dir_path,
        "matched": matched,
        "unmatched": unmatched,
        "docx_total": len(files),
    }


def audit_directory(dir_path, project_name=""):
    scan = scan_directory(dir_path, project_name)
    project_name = scan["project_name"]
    batch_id = db.execute(
        "INSERT INTO batches (project_name, source_dir, doc_total, doc_passed, avg_score, created_at)"
        " VALUES (?,?,?,?,?,?)", (project_name, dir_path, 0, 0, 0, db.now_str()))

    results = []
    for item in scan["matched"]:
        try:
            with open(item["file_path"], "rb") as fh:
                data = fh.read()
        except OSError as exc:
            results.append({
                "file_name": item["file_name"], "file_path": item["file_path"],
                "doc_type": item["doc_type"], "doc_type_name": item["doc_type_name"],
                "status": "error", "error": "读取文件失败：%s" % exc, "score": 0, "grade": "无法稽核",
            })
            continue
        res = run_audit(item["doc_type"], item["file_name"], data, project_name=project_name,
                        batch_id=batch_id, file_path=item["file_path"])
        results.append({
            "id": res.get("id"), "file_name": item["file_name"], "file_path": item["file_path"],
            "doc_type": item["doc_type"], "doc_type_name": item["doc_type_name"],
            "status": res["status"], "score": res["score"], "grade": res["grade"],
            "total_rules": res["total_rules"], "failed_rules": res["failed_rules"],
            "error": res.get("error", ""),
        })

    done = [r for r in results if r["status"] == "done"]
    passed_docs = len([r for r in done if r["score"] >= 60])
    avg = round(sum(r["score"] for r in done) / len(done), 1) if done else 0.0
    db.execute("UPDATE batches SET doc_total=?, doc_passed=?, avg_score=? WHERE id=?",
               (len(results), passed_docs, avg, batch_id))

    batch = db.query_one("SELECT * FROM batches WHERE id=?", (batch_id,))
    return {
        "batch": batch,
        "results": results,
        "unmatched": scan["unmatched"],
        "docx_total": scan["docx_total"],
    }
