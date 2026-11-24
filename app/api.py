# -*- coding: utf-8 -*-
"""HTTP API 与静态资源服务（Python 标准库实现）。"""
import base64
import binascii
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from . import audit, db, seed
from .checks import CHECKS, DIMENSIONS, checkers_meta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(BASE_DIR, "web")
MAX_UPLOAD = 40 * 1024 * 1024


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def pick_directory():
    """调起本机系统目录选择框，返回绝对路径。仅用于本机部署。"""
    if sys.platform == "darwin":
        cmd = ["osascript", "-e", 'POSIX path of (choose folder with prompt "请选择项目文档目录")']
    elif sys.platform.startswith("win"):
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
            "$d.Description = '请选择项目文档目录'; "
            "if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath }"
        )
        cmd = ["powershell", "-NoProfile", "-Command", script]
    elif shutil.which("zenity"):
        cmd = ["zenity", "--file-selection", "--directory", "--title=请选择项目文档目录"]
    elif shutil.which("kdialog"):
        cmd = ["kdialog", "--getexistingdirectory", os.path.expanduser("~")]
    else:
        raise ApiError("当前系统未找到目录选择组件，请手动输入路径", 501)

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        raise ApiError("未找到系统目录选择组件，请手动输入路径", 501)
    except subprocess.TimeoutExpired:
        raise ApiError("选择目录超时，请手动输入路径")

    if proc.returncode != 0:
        detail = (proc.stderr or "").strip()
        if "User canceled" in detail or "-128" in detail or proc.returncode == 1 and not detail:
            raise ApiError("已取消选择")
        raise ApiError("打开目录选择框失败：%s" % (detail or "未知错误"))

    path = (proc.stdout or "").strip()
    if not path:
        raise ApiError("已取消选择")
    if len(path) > 1:
        path = path.rstrip("/\\")
    if not os.path.isdir(path):
        raise ApiError("所选目录不可访问：%s" % path)
    return path


def _json_load(value, default):
    try:
        data = json.loads(value or "")
        return data if isinstance(data, (dict, list)) else default
    except ValueError:
        return default


def _rule_payload(body, existing=None):
    doc_type = (body.get("doc_type") or (existing or {}).get("doc_type") or "").strip()
    if not db.query_one("SELECT code FROM doc_types WHERE code=?", (doc_type,)):
        raise ApiError("文档类型不存在：%s" % doc_type)
    checker = (body.get("checker") or (existing or {}).get("checker") or "").strip()
    if checker not in CHECKS:
        raise ApiError("检查器不存在：%s" % checker)
    dimension = (body.get("dimension") or CHECKS[checker]["dimension"]).strip()
    if dimension not in [d["key"] for d in DIMENSIONS]:
        raise ApiError("稽核维度不合法：%s" % dimension)
    name = (body.get("name") or (existing or {}).get("name") or "").strip()
    if not name:
        raise ApiError("规则名称不能为空")
    params = body.get("params", (existing or {}).get("params", {}))
    if isinstance(params, str):
        params = _json_load(params, None)
        if params is None:
            raise ApiError("规则参数必须是合法 JSON 对象")
    if not isinstance(params, dict):
        raise ApiError("规则参数必须是 JSON 对象")
    severity = body.get("severity") or (existing or {}).get("severity") or "medium"
    if severity not in ("high", "medium", "low"):
        raise ApiError("严重级别不合法")
    enabled = body.get("enabled", (existing or {}).get("enabled", 1))
    return {
        "doc_type": doc_type,
        "dimension": dimension,
        "name": name,
        "checker": checker,
        "params": json.dumps(params, ensure_ascii=False),
        "severity": severity,
        "enabled": 1 if enabled in (1, True, "1", "true") else 0,
        "description": body.get("description", (existing or {}).get("description", "")),
        "sort_order": int(body.get("sort_order", (existing or {}).get("sort_order", 100))),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "DocAudit/1.0"

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    # ------------------------------------------------------------ 分发
    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _dispatch(self, method):
        parsed = urlparse(self.path)
        path = parsed.path
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        try:
            if path.startswith("/api/"):
                data = self._api(method, path, query)
                if isinstance(data, tuple):
                    payload, headers = data
                    if isinstance(payload, bytes):
                        self._raw(200, payload, headers)
                    else:
                        self._json(200, {"ok": True, "data": payload}, headers)
                else:
                    self._json(200, {"ok": True, "data": data})
            elif method == "GET":
                self._static(path)
            else:
                raise ApiError("接口不存在：%s" % path, 404)
        except ApiError as exc:
            self._json(exc.status, {"ok": False, "error": str(exc)})
        except Exception as exc:
            traceback.print_exc()
            self._json(500, {"ok": False, "error": "服务异常：%s" % exc})

    # ------------------------------------------------------------ API
    def _api(self, method, path, query):
        body = {}
        if method in ("POST", "PUT", "DELETE"):
            body = self._body_json()

        if method == "GET" and path == "/api/bootstrap":
            return {
                "doc_types": audit.doc_types(),
                "dimensions": DIMENSIONS,
                "checkers": checkers_meta(),
                "stats": self._stats(),
            }
        if method == "GET" and path == "/api/stats":
            return self._stats()
        if method == "GET" and path == "/api/doc-types":
            return audit.doc_types()
        if method == "GET" and path == "/api/checkers":
            return checkers_meta()

        if method == "GET" and path == "/api/rules":
            doc_type = query.get("docType", "")
            if not doc_type:
                raise ApiError("缺少参数 docType")
            rows = db.query("SELECT * FROM rules WHERE doc_type=? ORDER BY sort_order, id", (doc_type,))
            for r in rows:
                r["params"] = _json_load(r["params"], {})
            return rows

        if method == "POST" and path == "/api/rules":
            payload = _rule_payload(body)
            rule_id = db.execute(
                "INSERT INTO rules (doc_type, dimension, name, checker, params, severity, enabled,"
                " description, sort_order, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (payload["doc_type"], payload["dimension"], payload["name"], payload["checker"],
                 payload["params"], payload["severity"], payload["enabled"], payload["description"],
                 payload["sort_order"], db.now_str()))
            return {"id": rule_id}

        m = re.match(r"^/api/rules/(\d+)$", path)
        if m:
            rule_id = int(m.group(1))
            existing = db.query_one("SELECT * FROM rules WHERE id=?", (rule_id,))
            if not existing:
                raise ApiError("规则不存在", 404)
            existing["params"] = _json_load(existing["params"], {})
            if method == "PUT":
                payload = _rule_payload(body, existing)
                db.execute(
                    "UPDATE rules SET doc_type=?, dimension=?, name=?, checker=?, params=?, severity=?,"
                    " enabled=?, description=?, sort_order=?, updated_at=? WHERE id=?",
                    (payload["doc_type"], payload["dimension"], payload["name"], payload["checker"],
                     payload["params"], payload["severity"], payload["enabled"], payload["description"],
                     payload["sort_order"], db.now_str(), rule_id))
                return {"id": rule_id}
            if method == "DELETE":
                db.execute("DELETE FROM rules WHERE id=?", (rule_id,))
                return {"id": rule_id}
            raise ApiError("不支持的请求方法", 405)

        m = re.match(r"^/api/rules/(\d+)/toggle$", path)
        if m and method == "POST":
            rule_id = int(m.group(1))
            existing = db.query_one("SELECT * FROM rules WHERE id=?", (rule_id,))
            if not existing:
                raise ApiError("规则不存在", 404)
            enabled = 0 if existing["enabled"] else 1
            db.execute("UPDATE rules SET enabled=?, updated_at=? WHERE id=?",
                       (enabled, db.now_str(), rule_id))
            return {"id": rule_id, "enabled": enabled}

        if method == "POST" and path == "/api/rules/reset":
            doc_type = body.get("doc_type") or ""
            if doc_type not in seed.DEFAULT_RULES:
                raise ApiError("文档类型不存在：%s" % doc_type)
            seed.reset_rules(doc_type)
            return {"doc_type": doc_type}

        if method == "GET" and path == "/api/standards/versions":
            doc_type = query.get("docType", "")
            if not doc_type:
                raise ApiError("缺少参数 docType")
            row = db.query_one(
                "SELECT snapshot FROM standard_versions WHERE doc_type=? ORDER BY version_no DESC LIMIT 1",
                (doc_type,))
            snapshot = _json_load(row["snapshot"], []) if row else []
            return {"versions": audit.list_versions(doc_type), "current": snapshot}

        if method == "POST" and path == "/api/standards/publish":
            doc_type = body.get("doc_type") or ""
            if not db.query_one("SELECT code FROM doc_types WHERE code=?", (doc_type,)):
                raise ApiError("文档类型不存在：%s" % doc_type)
            version_no = audit.publish_version(doc_type, body.get("note", ""))
            return {"doc_type": doc_type, "version_no": version_no}

        if method == "POST" and path == "/api/audit/file":
            return self._audit_file(body)

        if method == "POST" and path == "/api/audit/directory":
            return self._audit_directory(body)

        if method == "POST" and path == "/api/system/pick-directory":
            return {"path": pick_directory()}

        if method == "GET" and path == "/api/runs":
            return self._list_runs(query)
        if method == "GET" and path == "/api/batches":
            return db.query("SELECT * FROM batches ORDER BY id DESC LIMIT 100")

        m = re.match(r"^/api/batches/(\d+)$", path)
        if m and method == "GET":
            batch_id = int(m.group(1))
            batch = db.query_one("SELECT * FROM batches WHERE id=?", (batch_id,))
            if not batch:
                raise ApiError("批次不存在", 404)
            batch["runs"] = db.query(
                "SELECT id, doc_type, file_name, score, grade, status, failed_rules, total_rules, created_at"
                " FROM audit_runs WHERE batch_id=? ORDER BY id", (batch_id,))
            return batch

        m = re.match(r"^/api/runs/(\d+)/export$", path)
        if m and method == "GET":
            run = audit.get_run(int(m.group(1)))
            if not run:
                raise ApiError("稽核记录不存在", 404)
            raw = json.dumps(run, ensure_ascii=False, indent=2).encode("utf-8")
            headers = {
                "Content-Type": "application/json; charset=utf-8",
                "Content-Disposition": 'attachment; filename="audit_run_%s.json"' % run["id"],
            }
            return raw, headers

        m = re.match(r"^/api/runs/(\d+)$", path)
        if m:
            run_id = int(m.group(1))
            if method == "GET":
                run = audit.get_run(run_id)
                if not run:
                    raise ApiError("稽核记录不存在", 404)
                return run
            if method == "DELETE":
                db.execute("DELETE FROM audit_findings WHERE run_id=?", (run_id,))
                db.execute("DELETE FROM audit_runs WHERE id=?", (run_id,))
                return {"id": run_id}

        raise ApiError("接口不存在：%s" % path, 404)

    def _stats(self):
        doc_count = db.query_one("SELECT COUNT(*) AS c FROM doc_types")["c"]
        rule_count = db.query_one("SELECT COUNT(*) AS c FROM rules WHERE enabled=1")["c"]
        run_count = db.query_one("SELECT COUNT(*) AS c FROM audit_runs")["c"]
        avg = db.query_one("SELECT AVG(score) AS s FROM audit_runs WHERE status='done'")
        fail_count = db.query_one(
            "SELECT COUNT(*) AS c FROM audit_findings WHERE status='fail' AND severity='high'")["c"]
        by_type = db.query(
            "SELECT r.doc_type, d.name AS doc_type_name, COUNT(*) AS runs, AVG(r.score) AS avg_score,"
            " SUM(CASE WHEN r.score < 60 THEN 1 ELSE 0 END) AS unqualified"
            " FROM audit_runs r LEFT JOIN doc_types d ON d.code = r.doc_type"
            " WHERE r.status='done' GROUP BY r.doc_type ORDER BY runs DESC")
        recent = db.query(
            "SELECT id, project_name, doc_type, file_name, score, grade, status, created_at"
            " FROM audit_runs ORDER BY id DESC LIMIT 8")
        return {
            "doc_type_count": doc_count,
            "rule_count": rule_count,
            "run_count": run_count,
            "avg_score": round(avg["s"], 1) if avg and avg["s"] is not None else 0,
            "high_fail_count": fail_count,
            "by_type": by_type,
            "recent": recent,
        }

    def _list_runs(self, query):
        where = []
        args = []
        doc_type = query.get("docType")
        if doc_type:
            where.append("doc_type=?")
            args.append(doc_type)
        keyword = query.get("keyword")
        if keyword:
            where.append("(file_name LIKE ? OR project_name LIKE ?)")
            args.extend(["%" + keyword + "%", "%" + keyword + "%"])
        limit = min(int(query.get("limit", 100)), 500)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        rows = db.query(
            "SELECT id, batch_id, project_name, doc_type, file_name, score, grade, status,"
            " total_rules, passed_rules, failed_rules, skipped_rules, created_at"
            " FROM audit_runs" + clause + " ORDER BY id DESC LIMIT ?", tuple(args + [limit]))
        names = {t["code"]: t["name"] for t in audit.doc_types()}
        for r in rows:
            r["doc_type_name"] = names.get(r["doc_type"], r["doc_type"])
        return rows

    def _audit_file(self, body):
        file_name = (body.get("file_name") or "").strip()
        content = body.get("content") or ""
        if not file_name:
            raise ApiError("缺少文件名")
        if not file_name.lower().endswith(".docx"):
            raise ApiError("仅支持 .docx 文件，请先将文档另存为 .docx")
        if "," in content and content.strip().startswith("data:"):
            content = content.split(",", 1)[1]
        try:
            data = base64.b64decode(content, validate=True)
        except (binascii.Error, ValueError):
            raise ApiError("文件内容解析失败，请重新上传")
        if not data:
            raise ApiError("文件内容为空")
        if len(data) > MAX_UPLOAD:
            raise ApiError("文件超过 40MB 限制")

        doc_type = (body.get("doc_type") or "").strip()
        if not doc_type or doc_type == "auto":
            detected = audit.detect_doc_type(file_name)
            if not detected:
                raise ApiError("无法根据文件名识别文档类型，请手动指定")
            doc_type = detected["code"]
        if not db.query_one("SELECT code FROM doc_types WHERE code=?", (doc_type,)):
            raise ApiError("文档类型不存在：%s" % doc_type)
        project_name = (body.get("project_name") or "").strip()
        return audit.run_audit(doc_type, file_name, data, project_name=project_name)

    def _audit_directory(self, body):
        path = (body.get("path") or "").strip()
        project_name = (body.get("project_name") or "").strip()
        if not path:
            raise ApiError("请填写项目文档目录的绝对路径")
        if not os.path.isabs(path):
            raise ApiError("请填写绝对路径，例如 /Users/xxx/project/docs")
        if body.get("dry_run"):
            return audit.scan_directory(path, project_name)
        return audit.audit_directory(path, project_name)

    # ------------------------------------------------------------ 基础能力
    def _body_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_UPLOAD * 1.5:
            raise ApiError("请求体过大", 413)
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError("请求体不是合法 JSON")
        return data if isinstance(data, dict) else {}

    def _raw(self, status, raw, extra_headers=None):
        self.send_response(status)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def _json(self, status, payload, extra_headers=None):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def _static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        rel = path.lstrip("/")
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not full.startswith(WEB_DIR) or not os.path.isfile(full):
            raise ApiError("页面不存在", 404)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as fh:
            raw = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(raw)
