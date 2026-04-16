# BUILD FIX SCRIPT FOR WINDOWS (V3 - Portable)
# Script này giúp giải quyết triệt để lỗi đường dẫn dài trên Windows.

$ProjectDir = $PSScriptRoot  # Tự động lấy thư mục chứa script
$VirtualDrive = "Z:"

Write-Host "--- BẮT ĐẦU QUY TRÌNH BUILD FIX ---" -ForegroundColor Cyan

# 1. Gỡ ổ ảo cũ nếu có
if (Test-Path $VirtualDrive) {
    subst $VirtualDrive /D
}

# 2. Tạo ổ đĩa ảo mới trỏ vào thư mục dự án
Write-Host "Đang ánh xạ thư mục dự án vào ổ đĩa ảo Z:..."
subst $VirtualDrive $ProjectDir

try {
    # 3. Chuyển sang ổ Z và chạy build
    # Chúng ta sử dụng cmd /c để đảm bảo lệnh gradlew chạy ổn định trên mọi phiên bản PowerShell
    Write-Host "Đang di chuyển vào Z:\android..."
    Set-Location "$VirtualDrive\android"
    
    Write-Host "Đang chạy lệnh Build Release (vui lòng đợi)..." -ForegroundColor Yellow
    cmd /c gradlew.bat clean assembleRelease
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n✔ BUILD THÀNH CÔNG!" -ForegroundColor Green
        Write-Host "File APK nằm tại: Z:\android\app\build\outputs\apk\release\app-release.apk" -ForegroundColor Green
    } else {
        Write-Host "`n✘ Build thất bại. Hãy kiểm tra các thông báo lỗi bên trên." -ForegroundColor Red
    }
}
finally {
    # 4. Quay lại và dọn dẹp
    Set-Location $ProjectDir
    subst $VirtualDrive /D
    Write-Host "--- HOÀN TẤT ---" -ForegroundColor Cyan
}
