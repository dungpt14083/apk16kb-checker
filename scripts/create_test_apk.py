#!/usr/bin/env python3
"""
Script tạo APK giả để test tool
Creates test APK with .so files having various alignments
"""

import zipfile
import struct
import io
import os


def make_elf_so(alignment: int, is_64bit: bool = True) -> bytes:
    """
    Tạo ELF .so nhỏ với LOAD segment có alignment cụ thể
    
    Args:
        alignment: Page alignment (vd: 4096 hoặc 16384)
        is_64bit: True = ELF64, False = ELF32
    
    Returns:
        bytes of ELF file
    """
    buf = bytearray()

    if is_64bit:
        # ELF64 header (64 bytes)
        # Magic
        buf += b'\x7fELF'
        buf += bytes([2])       # EI_CLASS = ELFCLASS64
        buf += bytes([1])       # EI_DATA  = ELFDATA2LSB (little-endian)
        buf += bytes([1])       # EI_VERSION = 1
        buf += bytes([0])       # EI_OSABI = ELFOSABI_NONE
        buf += bytes(8)         # EI_ABIVERSION + padding (8 bytes)
        # e_type = ET_DYN (3)
        buf += struct.pack('<H', 3)
        # e_machine = EM_AARCH64 (183)
        buf += struct.pack('<H', 183)
        # e_version = 1
        buf += struct.pack('<I', 1)
        # e_entry = 0
        buf += struct.pack('<Q', 0)
        # e_phoff = 64 (right after header)
        buf += struct.pack('<Q', 64)
        # e_shoff = 0
        buf += struct.pack('<Q', 0)
        # e_flags = 0
        buf += struct.pack('<I', 0)
        # e_ehsize = 64
        buf += struct.pack('<H', 64)
        # e_phentsize = 56 (64-bit phdr size)
        buf += struct.pack('<H', 56)
        # e_phnum = 1 (one PT_LOAD segment)
        buf += struct.pack('<H', 1)
        # e_shentsize = 64
        buf += struct.pack('<H', 64)
        # e_shnum = 0
        buf += struct.pack('<H', 0)
        # e_shstrndx = 0
        buf += struct.pack('<H', 0)

        # 64-bit Program Header (PT_LOAD) - 56 bytes
        # p_type = PT_LOAD (1)
        buf += struct.pack('<I', 1)
        # p_flags = PF_R | PF_X = 5
        buf += struct.pack('<I', 5)
        # p_offset = 0
        buf += struct.pack('<Q', 0)
        # p_vaddr = 0
        buf += struct.pack('<Q', 0)
        # p_paddr = 0
        buf += struct.pack('<Q', 0)
        # p_filesz
        buf += struct.pack('<Q', 256)
        # p_memsz
        buf += struct.pack('<Q', 256)
        # p_align = alignment (THE KEY FIELD)
        buf += struct.pack('<Q', alignment)

    else:
        # ELF32 header (52 bytes)
        buf += b'\x7fELF'
        buf += bytes([1])       # EI_CLASS = ELFCLASS32
        buf += bytes([1])       # EI_DATA  = LE
        buf += bytes([1])       # version
        buf += bytes([0])       # OSABI
        buf += bytes(8)         # padding
        buf += struct.pack('<H', 3)    # e_type = ET_DYN
        buf += struct.pack('<H', 40)   # e_machine = EM_ARM (40)
        buf += struct.pack('<I', 1)    # e_version
        buf += struct.pack('<I', 0)    # e_entry
        buf += struct.pack('<I', 52)   # e_phoff = 52 (after header)
        buf += struct.pack('<I', 0)    # e_shoff
        buf += struct.pack('<I', 0)    # e_flags
        buf += struct.pack('<H', 52)   # e_ehsize
        buf += struct.pack('<H', 32)   # e_phentsize (32-bit phdr = 32 bytes)
        buf += struct.pack('<H', 1)    # e_phnum
        buf += struct.pack('<H', 40)   # e_shentsize
        buf += struct.pack('<H', 0)    # e_shnum
        buf += struct.pack('<H', 0)    # e_shstrndx

        # 32-bit Program Header (PT_LOAD) - 32 bytes
        buf += struct.pack('<I', 1)          # p_type = PT_LOAD
        buf += struct.pack('<I', 0)          # p_offset
        buf += struct.pack('<I', 0)          # p_vaddr
        buf += struct.pack('<I', 0)          # p_paddr
        buf += struct.pack('<I', 256)        # p_filesz
        buf += struct.pack('<I', 256)        # p_memsz
        buf += struct.pack('<I', 5)          # p_flags = R|X
        buf += struct.pack('<I', alignment)  # p_align ← KEY FIELD

    # Pad to 256 bytes
    while len(buf) < 256:
        buf += b'\x00'

    return bytes(buf)


def create_test_apk(output_path: str):
    """Tạo APK test với nhiều loại .so"""
    
    # Các .so file sẽ tạo (name, abi, alignment, is_64bit)
    so_files = [
        # arm64-v8a — mix of compatible and incompatible
        ("libil2cpp.so",     "arm64-v8a",   4096,  True),   # ❌ 4KB
        ("libunity.so",      "arm64-v8a",   16384, True),   # ✅ 16KB
        ("libmain.so",       "arm64-v8a",   16384, True),   # ✅ 16KB
        ("libgame.so",       "arm64-v8a",   4096,  True),   # ❌ 4KB
        ("libcustom.so",     "arm64-v8a",   65536, True),   # ✅ 64KB (also OK)
        
        # armeabi-v7a — 32-bit
        ("libil2cpp.so",     "armeabi-v7a", 4096,  False),  # ❌
        ("libunity.so",      "armeabi-v7a", 4096,  False),  # ❌
        ("libmain.so",       "armeabi-v7a", 4096,  False),  # ❌
        
        # x86_64
        ("libil2cpp.so",     "x86_64",      4096,  True),   # ❌
        ("libunity.so",      "x86_64",      16384, True),   # ✅
        
        # x86
        ("libil2cpp.so",     "x86",         4096,  False),  # ❌
    ]

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as apk:
        # Thêm AndroidManifest.xml giả
        apk.writestr("AndroidManifest.xml", b'<?xml version="1.0"?><manifest/>')
        
        # Thêm classes.dex giả
        apk.writestr("classes.dex", b'\x64\x65\x78\n035\x00' + b'\x00'*100)
        
        # Thêm các .so file
        for name, abi, alignment, is_64 in so_files:
            elf_data = make_elf_so(alignment, is_64)
            path = f"lib/{abi}/{name}"
            apk.writestr(path, elf_data)
            kb = alignment // 1024
            print(f"  Added: {path} (align={alignment}B/{kb}KB, {'64-bit' if is_64 else '32-bit'})")
        
        # META-INF
        apk.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")

    print(f"\n✅ Test APK created: {output_path}")
    print(f"   Expected results:")
    print(f"   ❌ Không tương thích: libil2cpp.so(arm64), libgame.so(arm64), + armeabi-v7a, x86")
    print(f"   ✅ Tương thích: libunity.so(arm64-16KB), libmain.so(arm64-16KB), libcustom.so(64KB)")


if __name__ == "__main__":
    import sys
    output = sys.argv[1] if len(sys.argv) > 1 else "test_app.apk"
    create_test_apk(output)
