import urllib.request
import re
import os

url = "https://www.wch-ic.com/downloads/CH341SER_EXE.html"
headers = {'User-Agent': 'Mozilla/5.0'}
req = urllib.request.Request(url, headers=headers)

try:
    html = urllib.request.urlopen(req).read().decode('utf-8', errors='ignore')
    # Look for download link like /downloads/file/65.html or direct zip/exe link
    matches = re.findall(r'href=["\']([^"\']*CH341SER[^"\']*)["\']', html, re.IGNORECASE)
    print("Found download links:", matches)
    
    # Direct download link for CH341SER.EXE on WCH site:
    dl_url = "https://www.wch.cn/downloads/file/65.html"
    print(f"Downloading from {dl_url}...")
    
    dl_req = urllib.request.Request(dl_url, headers=headers)
    with urllib.request.urlopen(dl_req) as resp:
        content = resp.read()
        print(f"Downloaded {len(content)} bytes.")
        with open("CH341SER.exe", "wb") as f:
            f.write(content)
    print("CH341SER.exe saved successfully.")
except Exception as e:
    print("Error:", e)
