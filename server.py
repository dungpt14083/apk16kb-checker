"""
APK 16KB Page Size Checker - Web Server
Flask backend phục vụ API và static files
"""

import sys
import os
import json
import base64
import traceback
import logging
from pathlib import Path

# Thêm thư mục gốc vào path
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS

from core.compatibility_checker import (
    analyze_apk_bytes,
    export_json,
    export_markdown,
    export_html,
)

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# ─── Flask App ───────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="ui/dist", static_url_path="")
CORS(app)

# Giới hạn upload: 500MB
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024

# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve frontend"""
    return send_from_directory("ui", "index.html")


@app.route("/api/health")
def health():
    """Health check"""
    return jsonify({"status": "ok", "version": "1.0.0"})


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """
    Phân tích APK/AAB
    
    Request: multipart/form-data với field 'file'
    Response: JSON AnalysisReport
    """
    try:
        if "file" not in request.files:
            return jsonify({"error": "Không tìm thấy file trong request"}), 400

        f = request.files["file"]
        if not f.filename:
            return jsonify({"error": "Tên file không hợp lệ"}), 400

        filename = f.filename
        ext = os.path.splitext(filename)[1].lower()

        if ext not in (".apk", ".aab"):
            return jsonify({"error": f"Chỉ hỗ trợ file .apk và .aab, nhận được: {ext}"}), 400

        logger.info(f"Bắt đầu phân tích: {filename}")
        data = f.read()

        report = analyze_apk_bytes(data, filename)

        logger.info(
            f"Hoàn tất: {filename} | "
            f"Total={report.total_libraries} "
            f"OK={report.compatible_count} "
            f"Warn={report.warning_count} "
            f"Fail={report.incompatible_count}"
        )

        return jsonify(report.to_dict())

    except ValueError as e:
        logger.error(f"ValueError: {e}")
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        logger.error(f"Unexpected error: {traceback.format_exc()}")
        return jsonify({"error": f"Lỗi phân tích: {str(e)}"}), 500


@app.route("/api/export/<format>", methods=["POST"])
def export(format: str):
    """
    Export báo cáo
    
    Args:
        format: json | markdown | html
    
    Request: JSON report data
    Response: File download
    """
    try:
        from core.compatibility_checker import AnalysisReport, LibraryResult

        data = request.get_json()
        if not data:
            return jsonify({"error": "Không có dữ liệu"}), 400

        # Reconstruct report object từ JSON
        libraries = [LibraryResult(**lib) for lib in data.get("libraries", [])]
        report = AnalysisReport(
            file_name=data["file_name"],
            file_type=data["file_type"],
            file_size=data["file_size"],
            analysis_time=data["analysis_time"],
            total_libraries=data["total_libraries"],
            compatible_count=data["compatible_count"],
            warning_count=data["warning_count"],
            incompatible_count=data["incompatible_count"],
            unknown_count=data["unknown_count"],
            libraries=libraries,
            logs=data.get("logs", []),
            overall_status=data["overall_status"],
            summary=data["summary"],
        )

        base_name = os.path.splitext(report.file_name)[0]

        if format == "json":
            content = export_json(report)
            filename = f"{base_name}_16kb_report.json"
            mime = "application/json"

        elif format == "markdown":
            content = export_markdown(report)
            filename = f"{base_name}_16kb_report.md"
            mime = "text/markdown"

        elif format == "html":
            content = export_html(report)
            filename = f"{base_name}_16kb_report.html"
            mime = "text/html"

        else:
            return jsonify({"error": f"Format không hợp lệ: {format}"}), 400

        response = Response(
            content.encode("utf-8"),
            mimetype=mime,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": f"{mime}; charset=utf-8",
            }
        )
        return response

    except Exception as e:
        logger.error(f"Export error: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# Serve static files cho single-page app
@app.route("/<path:path>")
def serve_static(path):
    """Fallback cho SPA routing"""
    ui_dir = Path(__file__).parent / "ui"
    file_path = ui_dir / path
    if file_path.exists() and file_path.is_file():
        return send_from_directory(str(ui_dir), path)
    return send_from_directory(str(ui_dir), "index.html")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "false").lower() == "true"

    print(f"""
╔══════════════════════════════════════════════╗
║   APK 16KB Page Size Checker v1.0.0         ║
║   Tool kiểm tra tương thích Google Play     ║
╠══════════════════════════════════════════════╣
║   🌐 URL: http://localhost:{port}              ║
║   📁 Upload .apk hoặc .aab để phân tích     ║
║   🔧 Ctrl+C để dừng                         ║
╚══════════════════════════════════════════════╝
    """)

    app.run(host="0.0.0.0", port=port, debug=debug)
