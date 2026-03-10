"""
Compatibility Checker Module
Tổng hợp phân tích và tạo báo cáo tương thích 16KB page size
"""

import json
import datetime
import os
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field, asdict

from core.elf_parser import ElfInfo, CompatibilityStatus, parse_elf_from_bytes
from core.apk_parser import SoFileEntry, extract_so_files_from_bytes


@dataclass
class LibraryResult:
    """Kết quả kiểm tra một file .so"""
    name: str
    path: str
    abi: str
    file_size: int
    is_64bit: bool
    page_alignment: int
    status: str           # "compatible" | "warning" | "incompatible" | "unknown"
    status_icon: str      # ✅ ⚠️ ❌ ❓
    status_label: str     # Tương thích / Cảnh báo / Không tương thích
    description: str
    fix_suggestion: str
    error_message: str
    segment_count: int
    load_segment_count: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisReport:
    """Báo cáo tổng hợp phân tích"""
    file_name: str
    file_type: str          # apk / aab
    file_size: int
    analysis_time: str
    total_libraries: int
    compatible_count: int
    warning_count: int
    incompatible_count: int
    unknown_count: int
    libraries: List[LibraryResult] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)
    overall_status: str = "unknown"
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


# Map status → icon + label
STATUS_MAP = {
    CompatibilityStatus.COMPATIBLE:   ("✅", "Tương thích",       "compatible"),
    CompatibilityStatus.WARNING:      ("⚠️",  "Cảnh báo",          "warning"),
    CompatibilityStatus.INCOMPATIBLE: ("❌", "Không tương thích", "incompatible"),
    CompatibilityStatus.UNKNOWN:      ("❓", "Không xác định",    "unknown"),
}


def _elf_to_library_result(elf: ElfInfo) -> LibraryResult:
    """Chuyển đổi ElfInfo → LibraryResult"""
    icon, label, status_str = STATUS_MAP.get(
        elf.status, ("❓", "Không xác định", "unknown")
    )

    # Mô tả ngắn gọn
    if elf.page_alignment > 0:
        desc = f"Alignment: {elf.page_alignment:,} bytes ({elf.page_alignment // 1024}KB)"
    elif elf.error_message:
        desc = elf.error_message
    else:
        desc = "Không có thông tin alignment"

    return LibraryResult(
        name=elf.file_name,
        path=elf.file_path,
        abi=elf.abi,
        file_size=elf.file_size,
        is_64bit=elf.is_64bit,
        page_alignment=elf.page_alignment,
        status=status_str,
        status_icon=icon,
        status_label=label,
        description=desc,
        fix_suggestion=elf.fix_suggestion,
        error_message=elf.error_message,
        segment_count=len(elf.segments),
        load_segment_count=len(elf.load_segments),
    )


def analyze_apk_bytes(
    data: bytes,
    filename: str,
    progress_callback: Optional[Callable[[str, int, int], None]] = None
) -> AnalysisReport:
    """
    Phân tích APK/AAB từ bytes
    
    Args:
        data: Bytes của file APK/AAB
        filename: Tên file
        progress_callback: Callback(message, current, total)
    
    Returns:
        AnalysisReport
    """
    all_logs = []
    all_logs.append(f"🚀 Bắt đầu phân tích: {filename}")
    all_logs.append(f"📏 Kích thước file: {len(data):,} bytes")

    # Bước 1: Giải nén
    all_logs.append("─" * 40)
    all_logs.append("📦 BƯỚC 1: Giải nén APK/AAB...")

    if progress_callback:
        progress_callback("Đang giải nén...", 0, 100)

    so_files, extract_logs, file_type = extract_so_files_from_bytes(
        data, filename, progress_callback
    )
    all_logs.extend(extract_logs)

    # Bước 2: Phân tích ELF
    all_logs.append("─" * 40)
    all_logs.append(f"🔬 BƯỚC 2: Phân tích ELF headers ({len(so_files)} files)...")

    library_results = []
    total = len(so_files)

    for i, so_entry in enumerate(so_files):
        if progress_callback:
            progress_callback(
                f"Phân tích ELF: {so_entry.name}",
                i + 1, total
            )

        all_logs.append(f"  🔍 Parsing: {so_entry.name} [{so_entry.abi}]")

        elf = parse_elf_from_bytes(so_entry.data, so_entry.path, so_entry.abi)
        result = _elf_to_library_result(elf)
        library_results.append(result)

        # Log kết quả
        all_logs.append(
            f"     {result.status_icon} {result.status_label} "
            f"| Alignment: {result.page_alignment:,}B "
            f"| {'64-bit' if result.is_64bit else '32-bit'}"
        )

    # Bước 3: Tổng hợp
    all_logs.append("─" * 40)
    all_logs.append("📊 BƯỚC 3: Tổng hợp kết quả...")

    compatible   = sum(1 for r in library_results if r.status == "compatible")
    warnings     = sum(1 for r in library_results if r.status == "warning")
    incompatible = sum(1 for r in library_results if r.status == "incompatible")
    unknown      = sum(1 for r in library_results if r.status == "unknown")

    # Xác định trạng thái tổng thể
    if incompatible > 0:
        overall = "incompatible"
        summary = f"❌ KHÔNG TƯƠNG THÍCH: {incompatible} thư viện cần rebuild với 16KB alignment"
    elif warnings > 0:
        overall = "warning"
        summary = f"⚠️ CÓ CẢNH BÁO: {warnings} thư viện cần kiểm tra lại"
    elif compatible > 0:
        overall = "compatible"
        summary = f"✅ TƯƠNG THÍCH: Tất cả {compatible} thư viện hỗ trợ 16KB page size"
    else:
        overall = "unknown"
        summary = "❓ Không xác định được trạng thái tương thích"

    all_logs.append(f"  Tổng: {total} | ✅ {compatible} | ⚠️ {warnings} | ❌ {incompatible} | ❓ {unknown}")
    all_logs.append(f"  {summary}")
    all_logs.append("─" * 40)
    all_logs.append("🏁 Phân tích hoàn tất!")

    report = AnalysisReport(
        file_name=filename,
        file_type=file_type,
        file_size=len(data),
        analysis_time=datetime.datetime.now().isoformat(),
        total_libraries=total,
        compatible_count=compatible,
        warning_count=warnings,
        incompatible_count=incompatible,
        unknown_count=unknown,
        libraries=library_results,
        logs=all_logs,
        overall_status=overall,
        summary=summary,
    )

    return report


def export_json(report: AnalysisReport) -> str:
    """Export báo cáo sang JSON"""
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def export_markdown(report: AnalysisReport) -> str:
    """Export báo cáo sang Markdown"""
    lines = []
    lines.append(f"# Báo cáo Kiểm tra 16KB Page Size")
    lines.append(f"")
    lines.append(f"**File:** `{report.file_name}`")
    lines.append(f"**Loại:** {report.file_type.upper()}")
    lines.append(f"**Thời gian:** {report.analysis_time}")
    lines.append(f"**Kết quả:** {report.summary}")
    lines.append(f"")
    lines.append(f"## Tổng quan")
    lines.append(f"")
    lines.append(f"| Chỉ số | Số lượng |")
    lines.append(f"|--------|----------|")
    lines.append(f"| Tổng số thư viện | {report.total_libraries} |")
    lines.append(f"| ✅ Tương thích | {report.compatible_count} |")
    lines.append(f"| ⚠️ Cảnh báo | {report.warning_count} |")
    lines.append(f"| ❌ Không tương thích | {report.incompatible_count} |")
    lines.append(f"| ❓ Không xác định | {report.unknown_count} |")
    lines.append(f"")
    lines.append(f"## Chi tiết thư viện")
    lines.append(f"")
    lines.append(f"| Thư viện | ABI | Alignment | Trạng thái | Mô tả |")
    lines.append(f"|----------|-----|-----------|------------|-------|")

    for lib in report.libraries:
        alignment_str = f"{lib.page_alignment:,}B" if lib.page_alignment > 0 else "N/A"
        lines.append(
            f"| `{lib.name}` | {lib.abi} | {alignment_str} "
            f"| {lib.status_icon} {lib.status_label} | {lib.description} |"
        )

    # Hướng dẫn sửa lỗi
    incompatible_libs = [l for l in report.libraries if l.status == "incompatible"]
    if incompatible_libs:
        lines.append(f"")
        lines.append(f"## Hướng dẫn sửa lỗi")
        lines.append(f"")
        lines.append(f"### Rebuild với 16KB alignment")
        lines.append(f"")
        lines.append(f"**Sử dụng NDK flag:**")
        lines.append(f"```")
        lines.append(f"-Wl,-z,max-page-size=16384")
        lines.append(f"```")
        lines.append(f"")
        lines.append(f"**Trong `Android.mk`:**")
        lines.append(f"```makefile")
        lines.append(f"LOCAL_LDFLAGS += -Wl,-z,max-page-size=16384")
        lines.append(f"```")
        lines.append(f"")
        lines.append(f"**Trong `CMakeLists.txt`:**")
        lines.append(f"```cmake")
        lines.append(f"target_link_options(${{TARGET}} PRIVATE -Wl,-z,max-page-size=16384)")
        lines.append(f"```")
        lines.append(f"")
        lines.append(f"**Unity (Project Settings → Player → Android → Publishing Settings):**")
        lines.append(f"```")
        lines.append(f"Additional IL2CPP Arguments: -Wl,-z,max-page-size=16384")
        lines.append(f"```")

    return "\n".join(lines)


def export_html(report: AnalysisReport) -> str:
    """Export báo cáo sang HTML đẹp"""
    status_colors = {
        "compatible":   ("#10b981", "✅"),
        "warning":      ("#f59e0b", "⚠️"),
        "incompatible": ("#ef4444", "❌"),
        "unknown":      ("#6b7280", "❓"),
    }

    rows = ""
    for lib in report.libraries:
        color, icon = status_colors.get(lib.status, ("#6b7280", "❓"))
        align_str = f"{lib.page_alignment:,}B ({lib.page_alignment // 1024}KB)" if lib.page_alignment > 0 else "N/A"
        bit_str = "64-bit" if lib.is_64bit else "32-bit"
        fix_html = f"<div class='fix'>{lib.fix_suggestion.replace(chr(10), '<br>')}</div>" if lib.fix_suggestion else ""
        rows += f"""
        <tr>
            <td><code>{lib.name}</code></td>
            <td><span class="abi">{lib.abi}</span></td>
            <td>{bit_str}</td>
            <td class="align">{align_str}</td>
            <td><span class="badge" style="background:{color}20;color:{color};border:1px solid {color}40">{icon} {lib.status_label}</span></td>
            <td class="desc">{lib.description}{fix_html}</td>
        </tr>"""

    overall_color, overall_icon = status_colors.get(report.overall_status, ("#6b7280", "❓"))

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Báo cáo 16KB Page Size - {report.file_name}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0f172a; color: #e2e8f0; padding: 2rem; }}
  .header {{ background: linear-gradient(135deg, #1e293b, #0f172a); border: 1px solid #334155; border-radius: 12px; padding: 2rem; margin-bottom: 2rem; }}
  h1 {{ font-size: 1.8rem; color: #f1f5f9; margin-bottom: 0.5rem; }}
  .meta {{ color: #94a3b8; font-size: 0.9rem; }}
  .overall {{ display: inline-block; padding: 0.5rem 1rem; border-radius: 8px; font-weight: 600; margin-top: 1rem; background: {overall_color}20; color: {overall_color}; border: 1px solid {overall_color}40; }}
  .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 2rem; }}
  .stat {{ background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 1.5rem; text-align: center; }}
  .stat .num {{ font-size: 2.5rem; font-weight: 700; }}
  .stat .lbl {{ color: #94a3b8; font-size: 0.85rem; margin-top: 0.25rem; }}
  .compatible .num {{ color: #10b981; }}
  .warning .num {{ color: #f59e0b; }}
  .incompatible .num {{ color: #ef4444; }}
  .total .num {{ color: #60a5fa; }}
  table {{ width: 100%; border-collapse: collapse; background: #1e293b; border: 1px solid #334155; border-radius: 10px; overflow: hidden; }}
  th {{ background: #0f172a; padding: 0.75rem 1rem; text-align: left; font-size: 0.85rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }}
  td {{ padding: 0.75rem 1rem; border-bottom: 1px solid #334155; font-size: 0.9rem; vertical-align: top; }}
  tr:last-child td {{ border-bottom: none; }}
  code {{ background: #0f172a; padding: 0.2rem 0.4rem; border-radius: 4px; font-size: 0.85rem; color: #7dd3fc; }}
  .abi {{ background: #312e81; color: #a5b4fc; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.8rem; }}
  .badge {{ padding: 0.3rem 0.6rem; border-radius: 6px; font-size: 0.8rem; font-weight: 600; white-space: nowrap; }}
  .align {{ font-family: monospace; }}
  .fix {{ margin-top: 0.5rem; background: #0f172a; padding: 0.5rem; border-radius: 6px; font-family: monospace; font-size: 0.78rem; color: #fbbf24; white-space: pre-wrap; }}
  .fix-section {{ background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 1.5rem; margin-top: 2rem; }}
  .fix-section h2 {{ color: #f1f5f9; margin-bottom: 1rem; }}
  pre {{ background: #0f172a; padding: 1rem; border-radius: 8px; overflow: auto; color: #7dd3fc; border: 1px solid #334155; }}
  h2 {{ font-size: 1.2rem; color: #f1f5f9; margin-bottom: 1rem; }}
</style>
</head>
<body>
<div class="header">
  <h1>📱 Báo cáo Kiểm tra 16KB Page Size</h1>
  <div class="meta">
    <strong>File:</strong> {report.file_name} &nbsp;|&nbsp;
    <strong>Loại:</strong> {report.file_type.upper()} &nbsp;|&nbsp;
    <strong>Thời gian:</strong> {report.analysis_time}
  </div>
  <div class="overall">{overall_icon} {report.summary}</div>
</div>

<div class="stats">
  <div class="stat total"><div class="num">{report.total_libraries}</div><div class="lbl">Tổng thư viện</div></div>
  <div class="stat compatible"><div class="num">{report.compatible_count}</div><div class="lbl">✅ Tương thích</div></div>
  <div class="stat warning"><div class="num">{report.warning_count}</div><div class="lbl">⚠️ Cảnh báo</div></div>
  <div class="stat incompatible"><div class="num">{report.incompatible_count}</div><div class="lbl">❌ Không tương thích</div></div>
</div>

<h2>Chi tiết thư viện</h2>
<table>
  <thead>
    <tr>
      <th>Thư viện</th><th>ABI</th><th>Loại</th><th>Alignment</th><th>Trạng thái</th><th>Mô tả & Hướng dẫn</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>

<div class="fix-section">
  <h2>🔧 Hướng dẫn sửa lỗi</h2>
  <p style="color:#94a3b8;margin-bottom:1rem">Để rebuild với 16KB page alignment:</p>
  <p style="color:#94a3b8;margin-bottom:0.5rem"><strong>NDK / Clang flag:</strong></p>
  <pre>-Wl,-z,max-page-size=16384</pre>
  <p style="color:#94a3b8;margin:1rem 0 0.5rem"><strong>Android.mk:</strong></p>
  <pre>LOCAL_LDFLAGS += -Wl,-z,max-page-size=16384</pre>
  <p style="color:#94a3b8;margin:1rem 0 0.5rem"><strong>CMakeLists.txt:</strong></p>
  <pre>target_link_options(${{TARGET}} PRIVATE -Wl,-z,max-page-size=16384)</pre>
  <p style="color:#94a3b8;margin:1rem 0 0.5rem"><strong>Unity (IL2CPP):</strong></p>
  <pre>Additional IL2CPP Arguments: -Wl,-z,max-page-size=16384</pre>
</div>
</body>
</html>"""
