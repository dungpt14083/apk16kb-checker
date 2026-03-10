"""
ELF Parser Module
Phân tích ELF header của file .so để kiểm tra page alignment
"""

import struct
import os
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from enum import Enum


class CompatibilityStatus(Enum):
    COMPATIBLE = "compatible"       # ✅ Tương thích
    WARNING = "warning"             # ⚠️ Cảnh báo
    INCOMPATIBLE = "incompatible"   # ❌ Không tương thích
    UNKNOWN = "unknown"             # ❓ Không xác định


PAGE_SIZE_4KB  = 0x1000   # 4096
PAGE_SIZE_16KB = 0x4000   # 16384
PAGE_SIZE_64KB = 0x10000  # 65536

# ELF Magic bytes
ELF_MAGIC = b'\x7fELF'

# ELF e_type
ET_DYN = 3  # Shared object

# ELF program header types
PT_LOAD = 1
PT_GNU_RELRO = 0x6474e552
PT_GNU_STACK = 0x6474e551

# ELF class
ELFCLASS32 = 1
ELFCLASS64 = 2

# ELF data encoding
ELFDATA2LSB = 1  # Little endian
ELFDATA2MSB = 2  # Big endian


@dataclass
class ElfSegment:
    """Thông tin một segment trong ELF"""
    p_type: int
    p_offset: int
    p_vaddr: int
    p_paddr: int
    p_filesz: int
    p_memsz: int
    p_flags: int
    p_align: int

    @property
    def is_load(self) -> bool:
        return self.p_type == PT_LOAD

    @property
    def alignment_kb(self) -> int:
        return self.p_align // 1024 if self.p_align >= 1024 else 0


@dataclass
class ElfInfo:
    """Kết quả phân tích ELF file"""
    file_path: str
    file_name: str
    abi: str
    is_valid_elf: bool = False
    is_64bit: bool = False
    is_little_endian: bool = True
    e_type: int = 0
    segments: List[ElfSegment] = field(default_factory=list)
    max_load_alignment: int = 0
    min_load_alignment: int = 0
    page_alignment: int = 0
    status: CompatibilityStatus = CompatibilityStatus.UNKNOWN
    error_message: str = ""
    fix_suggestion: str = ""
    file_size: int = 0

    @property
    def load_segments(self) -> List[ElfSegment]:
        return [s for s in self.segments if s.is_load]


def _detect_abi(path: str) -> str:
    """Phát hiện ABI từ đường dẫn file"""
    path_lower = path.replace("\\", "/").lower()
    if "arm64-v8a" in path_lower:
        return "arm64-v8a"
    elif "armeabi-v7a" in path_lower:
        return "armeabi-v7a"
    elif "x86_64" in path_lower:
        return "x86_64"
    elif "x86" in path_lower:
        return "x86"
    return "unknown"


def _read_elf_header(data: bytes) -> Optional[dict]:
    """Đọc ELF header từ bytes"""
    if len(data) < 64:
        return None

    # Kiểm tra magic bytes
    if data[:4] != ELF_MAGIC:
        return None

    ei_class = data[4]     # 1=32bit, 2=64bit
    ei_data  = data[5]     # 1=LE, 2=BE

    is_64bit = (ei_class == ELFCLASS64)
    is_le    = (ei_data == ELFDATA2LSB)
    endian   = '<' if is_le else '>'

    try:
        if is_64bit:
            # 64-bit ELF header (64 bytes)
            fmt = f'{endian}HHIQQQIHHHHHH'
            size = struct.calcsize(fmt)
            if len(data) < 16 + size:
                return None
            fields = struct.unpack_from(fmt, data, 16)
            e_type, e_machine, e_version, e_entry, e_phoff, \
            e_shoff, e_flags, e_ehsize, e_phentsize, e_phnum, \
            e_shentsize, e_shnum, e_shstrndx = fields
        else:
            # 32-bit ELF header
            fmt = f'{endian}HHIIIIIHHHHHH'
            size = struct.calcsize(fmt)
            if len(data) < 16 + size:
                return None
            fields = struct.unpack_from(fmt, data, 16)
            e_type, e_machine, e_version, e_entry, e_phoff, \
            e_shoff, e_flags, e_ehsize, e_phentsize, e_phnum, \
            e_shentsize, e_shnum, e_shstrndx = fields

        return {
            'is_64bit': is_64bit,
            'is_le': is_le,
            'endian': endian,
            'e_type': e_type,
            'e_phoff': e_phoff,
            'e_phnum': e_phnum,
            'e_phentsize': e_phentsize,
        }
    except struct.error:
        return None


def _read_program_headers(data: bytes, header: dict) -> List[ElfSegment]:
    """Đọc program headers (segments)"""
    segments = []
    endian    = header['endian']
    is_64bit  = header['is_64bit']
    e_phoff   = header['e_phoff']
    e_phnum   = header['e_phnum']

    for i in range(e_phnum):
        offset = e_phoff + i * header['e_phentsize']
        try:
            if is_64bit:
                # 64-bit program header: p_type, p_flags, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_align
                fmt = f'{endian}IIQQQQQQ'
                if offset + struct.calcsize(fmt) > len(data):
                    break
                p_type, p_flags, p_offset_seg, p_vaddr, p_paddr, \
                p_filesz, p_memsz, p_align = struct.unpack_from(fmt, data, offset)
            else:
                # 32-bit program header: p_type, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_flags, p_align
                fmt = f'{endian}IIIIIIII'
                if offset + struct.calcsize(fmt) > len(data):
                    break
                p_type, p_offset_seg, p_vaddr, p_paddr, \
                p_filesz, p_memsz, p_flags, p_align = struct.unpack_from(fmt, data, offset)

            seg = ElfSegment(
                p_type=p_type,
                p_offset=p_offset_seg,
                p_vaddr=p_vaddr,
                p_paddr=p_paddr,
                p_filesz=p_filesz,
                p_memsz=p_memsz,
                p_flags=p_flags,
                p_align=p_align,
            )
            segments.append(seg)
        except struct.error:
            break

    return segments


def _determine_page_alignment(segments: List[ElfSegment]) -> int:
    """Xác định page alignment từ LOAD segments"""
    load_segments = [s for s in segments if s.is_load]
    if not load_segments:
        return 0

    # Lấy alignment lớn nhất từ LOAD segments (thường là p_align)
    alignments = [s.p_align for s in load_segments if s.p_align > 0]
    if not alignments:
        return 0

    # page_alignment = max alignment của các LOAD segments
    return max(alignments)


def _check_compatibility(elf_info: ElfInfo) -> Tuple[CompatibilityStatus, str, str]:
    """
    Kiểm tra tương thích 16KB page size
    
    Logic:
    - LOAD segment alignment >= 16384 → Compatible ✅
    - LOAD segment alignment == 4096  → Incompatible ❌ (cần rebuild với 16KB alignment)
    - Alignment khác (1, 0, ...)       → Warning ⚠️
    - Không có LOAD segment            → Unknown
    
    Returns: (status, description, fix_suggestion)
    """
    alignment = elf_info.page_alignment
    abi = elf_info.abi

    # ARM 64-bit cần kiểm tra nghiêm ngặt hơn
    is_arm64 = abi == "arm64-v8a"

    if alignment == 0:
        return (
            CompatibilityStatus.UNKNOWN,
            "Không tìm thấy LOAD segment",
            "Kiểm tra lại file .so có đúng định dạng không"
        )

    if alignment >= PAGE_SIZE_16KB:
        # Tương thích hoàn toàn
        return (
            CompatibilityStatus.COMPATIBLE,
            f"LOAD segment alignment = {alignment} bytes ({alignment//1024}KB) ✅",
            ""
        )
    elif alignment == PAGE_SIZE_4KB:
        # Không tương thích - cần rebuild
        if is_arm64:
            fix = (
                "Rebuild với NDK flags:\n"
                "  -Wl,-z,max-page-size=16384\n\n"
                "Hoặc trong Android.mk:\n"
                "  LOCAL_LDFLAGS += -Wl,-z,max-page-size=16384\n\n"
                "Hoặc trong CMakeLists.txt:\n"
                "  target_link_options(${TARGET} PRIVATE -Wl,-z,max-page-size=16384)"
            )
        else:
            fix = (
                f"ABI {abi} không bắt buộc 16KB, nhưng nên cập nhật:\n"
                "  -Wl,-z,max-page-size=16384"
            )
        return (
            CompatibilityStatus.INCOMPATIBLE,
            f"LOAD segment alignment = {alignment} bytes (4KB) - Google Play yêu cầu ≥ 16KB",
            fix
        )
    else:
        # Alignment không phổ biến
        return (
            CompatibilityStatus.WARNING,
            f"LOAD segment alignment = {alignment} bytes - Không phải giá trị chuẩn",
            (
                "Kiểm tra lại build flags. Alignment nên là 16384 (16KB) hoặc cao hơn.\n"
                "  -Wl,-z,max-page-size=16384"
            )
        )


def parse_elf_file(file_path: str, abi: str = "") -> ElfInfo:
    """
    Phân tích file ELF (.so) và trả về thông tin tương thích
    
    Args:
        file_path: Đường dẫn đến file .so
        abi: ABI của file (arm64-v8a, armeabi-v7a, x86, x86_64)
    
    Returns:
        ElfInfo object chứa kết quả phân tích
    """
    file_name = os.path.basename(file_path)
    detected_abi = abi if abi else _detect_abi(file_path)

    info = ElfInfo(
        file_path=file_path,
        file_name=file_name,
        abi=detected_abi,
    )

    try:
        info.file_size = os.path.getsize(file_path)
        with open(file_path, 'rb') as f:
            data = f.read()

        # Đọc ELF header
        header = _read_elf_header(data)
        if header is None:
            info.error_message = "File không phải ELF hợp lệ"
            info.status = CompatibilityStatus.UNKNOWN
            return info

        info.is_valid_elf = True
        info.is_64bit = header['is_64bit']
        info.is_little_endian = header['is_le']
        info.e_type = header['e_type']

        # Đọc program headers
        info.segments = _read_program_headers(data, header)

        # Tính page alignment
        info.page_alignment = _determine_page_alignment(info.segments)

        load_segs = info.load_segments
        if load_segs:
            alignments = [s.p_align for s in load_segs if s.p_align > 0]
            info.max_load_alignment = max(alignments) if alignments else 0
            info.min_load_alignment = min(alignments) if alignments else 0

        # Kiểm tra tương thích
        status, _, fix = _check_compatibility(info)
        info.status = status
        info.fix_suggestion = fix

    except PermissionError:
        info.error_message = "Không có quyền đọc file"
        info.status = CompatibilityStatus.UNKNOWN
    except Exception as e:
        info.error_message = f"Lỗi phân tích: {str(e)}"
        info.status = CompatibilityStatus.UNKNOWN

    return info


def parse_elf_from_bytes(data: bytes, file_name: str, abi: str = "") -> ElfInfo:
    """
    Phân tích ELF từ bytes (dùng khi giải nén từ APK/AAB)
    
    Args:
        data: Bytes của file .so
        file_name: Tên file
        abi: ABI của file
    
    Returns:
        ElfInfo object
    """
    info = ElfInfo(
        file_path=file_name,
        file_name=os.path.basename(file_name),
        abi=abi if abi else _detect_abi(file_name),
        file_size=len(data),
    )

    try:
        header = _read_elf_header(data)
        if header is None:
            info.error_message = "Không phải ELF hợp lệ"
            info.status = CompatibilityStatus.UNKNOWN
            return info

        info.is_valid_elf = True
        info.is_64bit = header['is_64bit']
        info.is_little_endian = header['is_le']
        info.e_type = header['e_type']

        info.segments = _read_program_headers(data, header)
        info.page_alignment = _determine_page_alignment(info.segments)

        load_segs = info.load_segments
        if load_segs:
            alignments = [s.p_align for s in load_segs if s.p_align > 0]
            info.max_load_alignment = max(alignments) if alignments else 0
            info.min_load_alignment = min(alignments) if alignments else 0

        status, _, fix = _check_compatibility(info)
        info.status = status
        info.fix_suggestion = fix

    except Exception as e:
        info.error_message = f"Lỗi: {str(e)}"
        info.status = CompatibilityStatus.UNKNOWN

    return info
