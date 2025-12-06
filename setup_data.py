import os
import urllib.request

# Ensure data directory exists
if not os.path.exists("data"):
    os.makedirs("data")

url = "https://github.com/lerocha/chinook-database/raw/master/ChinookDatabase/DataSources/Chinook_Sqlite.sqlite"
destination = "data/chinook.db"

print(f"Downloading Chinook Database to {destination}...")
try:
    urllib.request.urlretrieve(url, destination)
    print("✅ Download complete!")
    print(f"File size: {os.path.getsize(destination) / 1024:.2f} KB")
except Exception as e:
    print(f"❌ Error: {e}")