import os
from PIL import Image

def fix_images(root_dir):
    print(f"Scanning {root_dir}...")
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file == "splashscreen_logo.png":
                file_path = os.path.join(root, file)
                try:
                    with Image.open(file_path) as img:
                        fmt = img.format
                        if fmt != 'PNG':
                            print(f"Fixing {file_path}: Detected {fmt}, converting to PNG...")
                            # Save as real PNG
                            img.save(file_path, 'PNG')
                            print(f"Fixed: {file_path}")
                        else:
                            print(f"Skipping {file_path}: Already a PNG.")
                except Exception as e:
                    print(f"Error processing {file_path}: {e}")

if __name__ == "__main__":
    target = r"D:\Project_android_studio\So-Thu-Chi-React\SoThuChiRN\android\app\src\main\res"
    fix_images(target)
