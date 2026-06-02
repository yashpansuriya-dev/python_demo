"""
Remove-Item -Recurse -Force .git
"""

import os

# Loop from Day27 to Day40
for i in range(31, 35):
    folder_name = f"Day{i}"
    
    # Create folder (ignore if already exists)
    os.makedirs(folder_name, exist_ok=True)

print("Folders created successfully!")





