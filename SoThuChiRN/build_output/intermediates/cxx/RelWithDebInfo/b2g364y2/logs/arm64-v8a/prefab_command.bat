@echo off
"D:\\Android Studio Panda\\jbr\\bin\\java" ^
  --class-path ^
  "D:\\Project_android_studio\\So-Thu-Chi\\.gradle\\caches\\modules-2\\files-2.1\\com.google.prefab\\cli\\2.1.0\\aa32fec809c44fa531f01dcfb739b5b3304d3050\\cli-2.1.0-all.jar" ^
  com.google.prefab.cli.AppKt ^
  --build-system ^
  cmake ^
  --platform ^
  android ^
  --abi ^
  arm64-v8a ^
  --os-version ^
  24 ^
  --stl ^
  c++_shared ^
  --ndk-version ^
  27 ^
  --output ^
  "C:\\Users\\GuChu\\AppData\\Local\\Temp\\agp-prefab-staging7058210075682668114\\staged-cli-output" ^
  "D:\\Project_android_studio\\So-Thu-Chi\\.gradle\\caches\\8.14.3\\transforms\\95e397bfcdac2170cd7edb25e5c674ea\\transformed\\react-android-0.81.5-release\\prefab" ^
  "D:\\Project_android_studio\\So-Thu-Chi\\.gradle\\caches\\8.14.3\\transforms\\ed057027d7077e1ac7970355f1280bb9\\transformed\\hermes-android-0.81.5-release\\prefab" ^
  "D:\\Project_android_studio\\So-Thu-Chi\\.gradle\\caches\\8.14.3\\transforms\\75942e2706ceca671ce524a23fa3c4b6\\transformed\\fbjni-0.7.0\\prefab"
