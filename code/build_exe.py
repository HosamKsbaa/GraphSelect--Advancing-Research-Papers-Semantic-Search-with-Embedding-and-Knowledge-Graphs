"""GraphSelect Local Compilation Script.

Cleans build folders, installs PyInstaller if missing, compiles the application 
into a single-file executable, and performs automatic artifact cleanup.
"""

import os
import sys
import shutil
import subprocess

def main():
    print("==================================================")
    print("      GraphSelect Local Compilation Script        ")
    print("==================================================")
    
    # 1. Verify current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(current_dir)
    print(f"[*] Working directory: {current_dir}")
    
    # 2. Check for required files
    if not os.path.exists("main.py"):
        print("[-] Error: main.py not found in the current directory.")
        sys.exit(1)
        
    if not os.path.exists("static"):
        print("[-] Error: static/ directory not found in the current directory.")
        sys.exit(1)
        
    # 3. Check for PyInstaller
    try:
        import PyInstaller
        print(f"[+] PyInstaller detected: version {PyInstaller.__version__}")
    except ImportError:
        print("[*] PyInstaller is not installed. Installing it via pip...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
            print("[+] PyInstaller installed successfully!")
        except Exception as e:
            print(f"[-] Failed to install PyInstaller: {e}")
            sys.exit(1)
        
    # 4. Clean previous builds
    print("[*] Cleaning up any previous build configurations...")
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            try:
                shutil.rmtree(folder)
            except Exception as e:
                print(f"[-] Warning: could not clean folder '{folder}': {e}")
            
    if os.path.exists("GraphSelect.spec"):
        try:
            os.remove("GraphSelect.spec")
        except Exception as e:
            print(f"[-] Warning: could not clean GraphSelect.spec: {e}")
        
    # 5. Build executable
    print("[*] Initiating standalone executable compilation...")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--name", "GraphSelect",
        "--add-data", "static;static",
        "--collect-data", "rfc3987_syntax",
        "main.py"
    ]
    
    print(f"[*] Executing command: {' '.join(cmd)}")
    try:
        subprocess.check_call(cmd)
        exe_path = os.path.join(current_dir, "dist", "GraphSelect.exe")
        
        if os.path.exists(exe_path):
            print("\n==================================================")
            print("         SUCCESS: Standalone Build Successful!    ")
            print("==================================================")
            print(f"[+] Executable created: {exe_path}")
            print(f"[+] File size: {os.path.getsize(exe_path) / (1024*1024):.2f} MB")
        else:
            print("[-] Error: Compilation completed but executable was not found.")
            sys.exit(1)
        
        # 6. Clean up temporary build artifacts
        print("\n[*] Cleaning up temporary build artifacts (keeping dist/)...")
        if os.path.exists("build"):
            shutil.rmtree("build")
        if os.path.exists("GraphSelect.spec"):
            os.remove("GraphSelect.spec")
        print("[+] Cleanup completed successfully!")
        
    except subprocess.CalledProcessError as e:
        print(f"\n[-] Build process failed with exit code: {e.returncode}")
        sys.exit(1)

if __name__ == "__main__":
    main()
