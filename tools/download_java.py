import os
import sys
import urllib.request
import zipfile
from pathlib import Path

# Config
JRE_URL = "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jre/hotspot/normal/eclipse?project=jdk"
PROJECT_DIR = Path(__file__).parent.parent.resolve()
GENESIS_TOOLS = PROJECT_DIR / "genesis_tools"
JRE_ZIP = GENESIS_TOOLS / "jre.zip"
JRE_DIR = GENESIS_TOOLS / "jre"

def download_and_extract_jre():
    os.makedirs(GENESIS_TOOLS, exist_ok=True)
    
    print(f"[INFO] Downloading portable JRE from: {JRE_URL}")
    print("[INFO] This might take a minute...")
    
    # Custom User-Agent to avoid HTTP 403 Forbidden
    req = urllib.request.Request(
        JRE_URL, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    
    try:
        with urllib.request.urlopen(req) as response, open(JRE_ZIP, 'wb') as out_file:
            shutil_copyfileobj(response, out_file)
        print(f"[INFO] Downloaded: {JRE_ZIP}")
    except Exception as e:
        print(f"[ERROR] Failed to download JRE: {e}")
        return False
        
    print(f"[INFO] Extracting JRE to: {JRE_DIR}")
    try:
        if JRE_DIR.exists():
            import shutil
            shutil.rmtree(JRE_DIR)
            
        with zipfile.ZipFile(JRE_ZIP, 'r') as zip_ref:
            # The zip file contains a root directory, we need to extract and rename
            zip_ref.extractall(GENESIS_TOOLS)
            
        # Find the extracted directory name (e.g. jdk-17.0.7+7-jre)
        extracted_dirs = [d for d in GENESIS_TOOLS.iterdir() if d.is_dir() and d.name.startswith("jdk-")]
        if extracted_dirs:
            extracted_dir = extracted_dirs[0]
            os.rename(extracted_dir, JRE_DIR)
            print(f"[INFO] JRE successfully set up at: {JRE_DIR}")
        else:
            print("[ERROR] Extracted directory not found!")
            return False
            
    except Exception as e:
        print(f"[ERROR] Failed to extract JRE: {e}")
        return False
    finally:
        # Clean up zip
        if JRE_ZIP.exists():
            os.remove(JRE_ZIP)
            
    return True

def shutil_copyfileobj(fsrc, fdst, length=16*1024):
    while True:
        buf = fsrc.read(length)
        if not buf:
            break
        fdst.write(buf)

if __name__ == '__main__':
    success = download_and_extract_jre()
    sys.exit(0 if success else 1)
