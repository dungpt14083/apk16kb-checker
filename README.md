# APK 16KB Page Size Checker

> 🔧 Tool kiểm tra tương thích **16KB memory page size** cho Android APK/AAB  
> Dành cho Android game developer (Unity, Unreal, NDK)

---

## Tính năng

- ✅ Phân tích ELF header của tất cả file `.so` trong APK/AAB
- ✅ Kiểm tra LOAD segment alignment (4KB vs 16KB)  
- ✅ Hỗ trợ: `arm64-v8a`, `armeabi-v7a`, `x86`, `x86_64`
- ✅ Dashboard web với drag & drop (tiếng Việt)
- ✅ CLI tool với màu sắc
- ✅ Export JSON / Markdown / HTML report
- ✅ Gợi ý sửa lỗi chi tiết cho Unity, CMake, NDK

---

## Cài đặt

```bash
# Clone hoặc giải nén project
cd apk16kb-checker

# Cài dependencies (chỉ cần cho web mode)
pip install flask flask-cors

# Không cần pip gì cho CLI mode!
```

---

## Sử dụng

### 🖥️ Web UI (khuyến nghị)

```bash
# Khởi động web server
python3 server.py

# Mở trình duyệt
# → http://localhost:5000
```

Kéo thả file APK/AAB vào giao diện hoặc dùng file picker.

### 💻 CLI Tool

```bash
# Kiểm tra cơ bản
python3 apk16kb_checker.py myapp.apk

# Export báo cáo JSON
python3 apk16kb_checker.py myapp.apk --export json

# Export HTML report
python3 apk16kb_checker.py myapp.apk --export html

# Xem log chi tiết
python3 apk16kb_checker.py myapp.apk --verbose

# Dùng trong CI/CD (exit code: 0=OK, 1=warning, 2=lỗi)
python3 apk16kb_checker.py myapp.apk && echo "PASSED" || echo "FAILED"
```

### 🧪 Tạo APK test

```bash
python3 scripts/create_test_apk.py test_app.apk
python3 apk16kb_checker.py test_app.apk
```

---

## Cấu trúc project

```
apk16kb-checker/
├── core/
│   ├── elf_parser.py          # ELF header parser (pure Python)
│   ├── apk_parser.py          # APK/AAB ZIP extractor
│   └── compatibility_checker.py  # Analysis + report builder
├── ui/
│   └── index.html             # Dashboard web UI (single file)
├── scripts/
│   └── create_test_apk.py     # Tạo APK test
├── apk16kb_checker.py         # CLI entry point
├── server.py                  # Flask web server
├── requirements.txt
└── README.md
```

---

## Cách đọc kết quả

| Trạng thái | Ý nghĩa | Alignment |
|---|---|---|
| ✅ Tương thích | Library OK, hỗ trợ 16KB | ≥ 16384B |
| ⚠️ Cảnh báo | Alignment không phổ biến, cần kiểm tra | Khác 4KB/16KB |
| ❌ Không tương thích | Library cần rebuild | = 4096B |
| ❓ Không xác định | Không đọc được ELF | — |

---

## Sửa lỗi

Khi thấy ❌, thêm flag này vào linker:

### NDK / Clang
```
-Wl,-z,max-page-size=16384
```

### Android.mk
```makefile
LOCAL_LDFLAGS += -Wl,-z,max-page-size=16384
```

### CMakeLists.txt
```cmake
target_link_options(${TARGET} PRIVATE -Wl,-z,max-page-size=16384)
```

### Unity IL2CPP
```
Project Settings → Player → Android → Additional IL2CPP Arguments:
-Wl,-z,max-page-size=16384
```

### app/build.gradle
```groovy
android {
  defaultConfig {
    externalNativeBuild {
      cmake {
        arguments "-DANDROID_LDFLAGS=-Wl,-z,max-page-size=16384"
      }
    }
  }
}
```

---

## Timeline Google Play

| Thời điểm | Yêu cầu |
|---|---|
| **11/2025** | App mới bắt buộc hỗ trợ 16KB |
| **6/2026** | App update (existing) bắt buộc hỗ trợ 16KB |

---

## Deploy Web (Production)

```bash
# Dùng gunicorn
pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:5000 server:app

# Docker
docker build -t apk16kb-checker .
docker run -p 5000:5000 apk16kb-checker
```

---

## CI/CD Integration

```yaml
# GitHub Actions example
- name: Check APK 16KB compatibility
  run: |
    python3 apk16kb_checker.py app-release.apk --export json --output report.json
    cat report.json | python3 -c "import json,sys; r=json.load(sys.stdin); sys.exit(2 if r['incompatible_count']>0 else 0)"
```

---

## License

MIT — Dùng tự do cho dự án nội bộ.
