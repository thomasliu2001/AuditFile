#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""项目文档稽核平台启动入口。"""
import os
import sys
import webbrowser
from http.server import ThreadingHTTPServer

from app import api, db, seed


def main():
    db.init_db()
    seed.ensure_seed()

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8765"))
    try:
        server = ThreadingHTTPServer((host, port), api.Handler)
    except OSError as exc:
        print("启动失败：%s" % exc)
        print("端口 %d 可能已被占用，可用 PORT=8766 python3 server.py 更换端口" % port)
        sys.exit(1)

    url = "http://%s:%d/" % (host, port)
    print("=" * 58)
    print(" 项目验收文档稽核平台已启动")
    print(" 访问地址: %s" % url)
    print(" 数据文件: %s" % db.DB_PATH)
    print(" 按 Ctrl+C 停止服务")
    print("=" * 58)
    if "--open" in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
