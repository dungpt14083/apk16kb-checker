#!/usr/bin/env python3
"""
APK 16KB Page Size Checker — CLI
Dùng dòng lệnh: python3 apk16kb_checker.py myapp.apk
"""

import sys
import os
import argparse
import json

# Thêm thư mục gốc vào path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.compatibility_checker import analyze_apk_bytes, export_json, export_markdown, export_html


BANNER = """
╔══════════════════════════════════════════════════════╗
║   APK 16KB Page Size Checker v1.0.0                 ║
║   Kiểm tra tương thích Google Play requirement      ║
╚══════════════════════════════════════════════════════╝"""

STATUS_ICONS = {
    "compatible":   "✅",
    "warning":      "⚠️ ",
    "incompatible": "❌",
    "unknown":      "❓",
}

def colorize(text, color):
    """ANSI color codes"""
    colors = {
        "green":  "\033[92m",
        "yellow": "\033[93m",
        "red":    "\033[91m",
        "blue":   "\033[94m",
        "cyan":   "\033[96m",
        "gray":   "\033[90m",
        "bold":   "\033[1m",
        "reset":  "\033[0m",
    }
    return f"{colors.get(color,'')}{text}{colors['reset']}"


def print_report(report, verbose=False):
    """In báo cáo ra console"""
    print(colorize(BANNER, "blue"))
    print()

    # File info
    print(colorize(f"📱 File: {report.file_name}", "bold"))
    print(colorize(f"📦 Loại: {report.file_type.upper()} | Size: {report.file_size:,} bytes", "gray"))
    print(colorize(f"⏰ Thời gian: {report.analysis_time}", "gray"))
    print()

    # Overall status
    status_colors = {
        "compatible":   "green",
        "warning":      "yellow",
        "incompatible": "red",
        "unknown":      "gray",
    }
    color = status_colors.get(report.overall_status, "gray")
    print(colorize(f"{'─'*55}", "gray"))
    print(colorize(f"KẾT QUẢ: {report.summary}", color))
    print(colorize(f"{'─'*55}", "gray"))
    print()

    # Stats
    print(colorize(f"  📊 Tổng số thư viện : {report.total_libraries}", "bold"))
    print(colorize(f"  ✅ Tương thích       : {report.compatible_count}", "green"))
    print(colorize(f"  ⚠️  Cảnh báo          : {report.warning_count}", "yellow"))
    print(colorize(f"  ❌ Không tương thích : {report.incompatible_count}", "red"))
    if report.unknown_count > 0:
        print(colorize(f"  ❓ Không xác định    : {report.unknown_count}", "gray"))
    print()

    # Library table
    if report.libraries:
        print(colorize(f"{'─'*55}", "gray"))
        print(colorize(f"  {'Thư viện':<30} {'ABI':<14} {'Align':>8}  Trạng thái", "bold"))
        print(colorize(f"{'─'*55}", "gray"))

        for lib in report.libraries:
            icon  = STATUS_ICONS.get(lib.status, "❓")
            color = status_colors.get(lib.status, "gray")
            align_str = f"{lib.page_alignment:>6,}B" if lib.page_alignment > 0 else "   N/A "
            name_str  = lib.name[:29] if len(lib.name) > 29 else lib.name

            line = f"  {name_str:<30} {lib.abi:<14} {align_str}  {icon} {lib.status_label}"
            print(colorize(line, color))

            if verbose and lib.fix_suggestion:
                for fix_line in lib.fix_suggestion.split('\n'):
                    print(colorize(f"    💡 {fix_line}", "cyan"))

        print(colorize(f"{'─'*55}", "gray"))
        print()

    # Fix suggestions
    incompatible = [l for l in report.libraries if l.status == "incompatible"]
    if incompatible:
        print(colorize("🔧 HƯỚNG DẪN SỬA LỖI:", "yellow"))
        print()
        print(colorize("  Rebuild với NDK flag:", "bold"))
        print(colorize("    -Wl,-z,max-page-size=16384", "cyan"))
        print()
        print(colorize("  Android.mk:", "bold"))
        print(colorize("    LOCAL_LDFLAGS += -Wl,-z,max-page-size=16384", "cyan"))
        print()
        print(colorize("  CMakeLists.txt:", "bold"))
        print(colorize("    target_link_options(${TARGET} PRIVATE -Wl,-z,max-page-size=16384)", "cyan"))
        print()
        print(colorize("  Unity IL2CPP:", "bold"))
        print(colorize("    Project Settings → Player → Android → Additional IL2CPP Arguments:", "gray"))
        print(colorize("    -Wl,-z,max-page-size=16384", "cyan"))
        print()

    # Verbose logs
    if verbose:
        print(colorize("📋 LOGS:", "gray"))
        for log in report.logs[-30:]:  # Hiện 30 log cuối
            print(colorize(f"  {log}", "gray"))


def main():
    parser = argparse.ArgumentParser(
        description="APK 16KB Page Size Checker — Kiểm tra tương thích Google Play",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ sử dụng:
  python3 apk16kb_checker.py myapp.apk
  python3 apk16kb_checker.py myapp.aab --export json
  python3 apk16kb_checker.py myapp.apk --export html --output report.html
  python3 apk16kb_checker.py myapp.apk --verbose
        """
    )
    parser.add_argument("file", help="Đường dẫn đến file APK hoặc AAB")
    parser.add_argument("--export", choices=["json", "markdown", "html"], help="Export báo cáo")
    parser.add_argument("--output", help="Đường dẫn file output (mặc định: <filename>_16kb_report.<ext>)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Hiện log chi tiết")
    parser.add_argument("--quiet",   "-q", action="store_true", help="Chỉ in kết quả tóm tắt")

    args = parser.parse_args()

    # Kiểm tra file tồn tại
    if not os.path.exists(args.file):
        print(colorize(f"❌ Không tìm thấy file: {args.file}", "red"))
        sys.exit(1)

    ext = os.path.splitext(args.file)[1].lower()
    if ext not in (".apk", ".aab"):
        print(colorize(f"❌ Chỉ hỗ trợ .apk và .aab, nhận được: {ext}", "red"))
        sys.exit(1)

    # Đọc file
    if not args.quiet:
        print(colorize(f"📖 Đang đọc file: {args.file}...", "gray"))

    with open(args.file, 'rb') as f:
        data = f.read()

    # Phân tích
    if not args.quiet:
        print(colorize("🔍 Đang phân tích...", "gray"))

    def progress(msg, cur, total):
        if not args.quiet:
            pct = int(cur/total*100) if total > 0 else 0
            print(colorize(f"\r  [{pct:3d}%] {msg[:50]:<50}", "gray"), end='', flush=True)

    report = analyze_apk_bytes(data, os.path.basename(args.file), progress if not args.quiet else None)
    if not args.quiet:
        print()

    # In báo cáo
    if not args.quiet:
        print_report(report, verbose=args.verbose)

    # Export
    if args.export:
        base = os.path.splitext(os.path.basename(args.file))[0]

        if args.export == "json":
            content = export_json(report)
            out_ext = "json"
        elif args.export == "markdown":
            content = export_markdown(report)
            out_ext = "md"
        elif args.export == "html":
            content = export_html(report)
            out_ext = "html"

        output_path = args.output or f"{base}_16kb_report.{out_ext}"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(colorize(f"✅ Đã export báo cáo: {output_path}", "green"))

    # Exit code
    if report.incompatible_count > 0:
        sys.exit(2)  # Có lỗi
    elif report.warning_count > 0:
        sys.exit(1)  # Có cảnh báo
    else:
        sys.exit(0)  # OK


if __name__ == "__main__":
    main()
