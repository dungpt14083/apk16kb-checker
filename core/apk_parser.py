"""
APK / AAB Parser Module
Giải nén APK và AAB, tìm và trả về tất cả file .so
"""

import zipfile
import io
import os
import logging
from typing import List, Tuple, Callable, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Thư mục ABI trong APK/AAB
ABI_DIRS = {
    "arm64-v8a":   "lib/arm64-v8a/",
    "armeabi-v7a": "lib/armeabi-v7a/",
    "x86":         "lib/x86/",
    "x86_64":      "lib/x86_64/",
}


@dataclass
class SoFileEntry:
    """Đại diện cho một file .so tìm thấy trong APK/AAB"""
    name: str           # Tên file (vd: libil2cpp.so)
    path: str           # Đường dẫn trong archive (vd: lib/arm64-v8a/libil2cpp.so)
    abi: str            # ABI (vd: arm64-v8a)
    data: bytes         # Nội dung file
    size: int           # Kích thước file (bytes)


def _detect_abi_from_path(path: str) -> str:
    """Phát hiện ABI từ đường dẫn trong archive"""
    path_normalized = path.replace("\\", "/")
    for abi, prefix in ABI_DIRS.items():
        if path_normalized.startswith(prefix) or f"/{abi}/" in path_normalized:
            return abi
    return "unknown"


def _is_so_file(path: str) -> bool:
    """Kiểm tra xem file có phải là .so không"""
    return path.endswith(".so") and not path.startswith("__MACOSX")


def extract_so_files_from_apk(
    file_path: str,
    progress_callback: Optional[Callable[[str, int, int], None]] = None
) -> Tuple[List[SoFileEntry], List[str]]:
    """
    Giải nén APK và trích xuất tất cả file .so
    
    Args:
        file_path: Đường dẫn đến file APK
        progress_callback: Callback(message, current, total)
    
    Returns:
        (list of SoFileEntry, list of log messages)
    """
    so_files = []
    logs = []

    try:
        logs.append(f"📂 Mở file APK: {os.path.basename(file_path)}")

        with zipfile.ZipFile(file_path, 'r') as apk:
            all_entries = apk.namelist()
            so_entries = [e for e in all_entries if _is_so_file(e)]

            logs.append(f"📋 Tìm thấy {len(all_entries)} files trong APK")
            logs.append(f"🔍 Phát hiện {len(so_entries)} file .so")

            for i, entry in enumerate(so_entries):
                abi = _detect_abi_from_path(entry)
                name = os.path.basename(entry)

                if progress_callback:
                    progress_callback(f"Đang đọc: {name}", i + 1, len(so_entries))

                logs.append(f"  → Đọc: {entry} (ABI: {abi})")

                try:
                    data = apk.read(entry)
                    so_files.append(SoFileEntry(
                        name=name,
                        path=entry,
                        abi=abi,
                        data=data,
                        size=len(data),
                    ))
                except Exception as e:
                    logs.append(f"  ⚠️ Lỗi đọc {entry}: {e}")

        logs.append(f"✅ Giải nén xong: {len(so_files)} file .so")

    except zipfile.BadZipFile:
        logs.append("❌ File không phải APK hợp lệ (bad zip)")
        raise ValueError("File không phải APK hợp lệ")
    except Exception as e:
        logs.append(f"❌ Lỗi: {e}")
        raise

    return so_files, logs


def extract_so_files_from_aab(
    file_path: str,
    progress_callback: Optional[Callable[[str, int, int], None]] = None
) -> Tuple[List[SoFileEntry], List[str]]:
    """
    Giải nén AAB và trích xuất tất cả file .so
    AAB có cấu trúc tương tự ZIP nhưng .so nằm trong:
    base/lib/arm64-v8a/ hoặc splits/...
    
    Args:
        file_path: Đường dẫn đến file AAB
        progress_callback: Callback(message, current, total)
    
    Returns:
        (list of SoFileEntry, list of log messages)
    """
    so_files = []
    logs = []

    try:
        logs.append(f"📦 Mở file AAB: {os.path.basename(file_path)}")

        with zipfile.ZipFile(file_path, 'r') as aab:
            all_entries = aab.namelist()
            logs.append(f"📋 Tìm thấy {len(all_entries)} files trong AAB")

            # AAB có thể có cấu trúc: base/lib/arm64-v8a/*.so
            so_entries = []
            for entry in all_entries:
                if not entry.endswith(".so"):
                    continue
                if "__MACOSX" in entry:
                    continue
                so_entries.append(entry)

            logs.append(f"🔍 Phát hiện {len(so_entries)} file .so trong AAB")

            for i, entry in enumerate(so_entries):
                # AAB path: base/lib/arm64-v8a/libfoo.so
                # Detect ABI từ path
                abi = "unknown"
                for abi_name in ABI_DIRS.keys():
                    if f"/{abi_name}/" in entry or entry.startswith(f"lib/{abi_name}/"):
                        abi = abi_name
                        break

                name = os.path.basename(entry)

                if progress_callback:
                    progress_callback(f"Đang đọc: {name}", i + 1, len(so_entries))

                logs.append(f"  → Đọc: {entry} (ABI: {abi})")

                try:
                    data = aab.read(entry)
                    so_files.append(SoFileEntry(
                        name=name,
                        path=entry,
                        abi=abi,
                        data=data,
                        size=len(data),
                    ))
                except Exception as e:
                    logs.append(f"  ⚠️ Lỗi đọc {entry}: {e}")

        logs.append(f"✅ Giải nén xong: {len(so_files)} file .so")

    except zipfile.BadZipFile:
        logs.append("❌ File AAB không hợp lệ")
        raise ValueError("File AAB không hợp lệ")
    except Exception as e:
        logs.append(f"❌ Lỗi: {e}")
        raise

    return so_files, logs


def extract_so_files(
    file_path: str,
    progress_callback: Optional[Callable[[str, int, int], None]] = None
) -> Tuple[List[SoFileEntry], List[str], str]:
    """
    Tự động phát hiện APK hoặc AAB và giải nén
    
    Returns:
        (list of SoFileEntry, list of logs, file_type: 'apk'|'aab')
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".apk":
        so_files, logs = extract_so_files_from_apk(file_path, progress_callback)
        return so_files, logs, "apk"
    elif ext == ".aab":
        so_files, logs = extract_so_files_from_aab(file_path, progress_callback)
        return so_files, logs, "aab"
    else:
        # Thử đọc như ZIP và auto-detect
        try:
            so_files, logs = extract_so_files_from_apk(file_path, progress_callback)
            return so_files, logs, "apk"
        except Exception:
            raise ValueError(f"Không hỗ trợ định dạng file: {ext}")


def extract_so_files_from_bytes(
    data: bytes,
    filename: str,
    progress_callback: Optional[Callable[[str, int, int], None]] = None
) -> Tuple[List[SoFileEntry], List[str], str]:
    """
    Giải nén từ bytes (dùng khi upload từ browser)
    
    Args:
        data: Bytes của file APK/AAB
        filename: Tên file gốc
        progress_callback: Callback
    
    Returns:
        (list of SoFileEntry, list of logs, file_type)
    """
    so_files = []
    logs = []
    ext = os.path.splitext(filename)[1].lower()
    file_type = "aab" if ext == ".aab" else "apk"

    try:
        logs.append(f"📂 Đang xử lý: {filename} ({len(data):,} bytes)")

        buffer = io.BytesIO(data)
        with zipfile.ZipFile(buffer, 'r') as zf:
            all_entries = zf.namelist()
            so_entries = [e for e in all_entries if e.endswith(".so") and "__MACOSX" not in e]

            logs.append(f"📋 Tổng files trong archive: {len(all_entries)}")
            logs.append(f"🔍 Phát hiện {len(so_entries)} file .so")

            for i, entry in enumerate(so_entries):
                abi = "unknown"
                for abi_name in ABI_DIRS.keys():
                    if f"/{abi_name}/" in entry or f"lib/{abi_name}/" in entry:
                        abi = abi_name
                        break

                name = os.path.basename(entry)

                if progress_callback:
                    progress_callback(f"Đọc: {name}", i + 1, len(so_entries))

                logs.append(f"  → {entry} [ABI: {abi}]")

                try:
                    file_data = zf.read(entry)
                    so_files.append(SoFileEntry(
                        name=name,
                        path=entry,
                        abi=abi,
                        data=file_data,
                        size=len(file_data),
                    ))
                except Exception as e:
                    logs.append(f"  ⚠️ Lỗi: {e}")

        logs.append(f"✅ Hoàn tất: {len(so_files)} thư viện tìm thấy")

    except zipfile.BadZipFile:
        raise ValueError(f"File {filename} không phải ZIP/APK/AAB hợp lệ")
    except Exception as e:
        raise ValueError(f"Lỗi đọc file: {e}")

    return so_files, logs, file_type
