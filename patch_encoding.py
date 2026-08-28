import glob
import re

for filepath in glob.glob("*.py"):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Match any sys.stdout.reconfigure statement not inside try-except
    pattern = r'(?<!try:\n    )if hasattr\(sys\.stdout, ["\']reconfigure["\']\):\n\s+sys\.stdout\.reconfigure\(encoding=["\']utf-8["\']\)'
    replacement = "try:\n    if hasattr(sys.stdout, 'reconfigure'):\n        sys.stdout.reconfigure(encoding='utf-8')\nexcept Exception:\n    pass"

    new_content = re.sub(pattern, replacement, content)
    if new_content != content:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"Patched {filepath}")

print("All files safely patched for Streamlit!")
