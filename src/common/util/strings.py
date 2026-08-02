# ==== file_id: SOM-EXT-8073-v1.0.0 name: strings.py date: 2026-06-08 ====
# ==== file_id: SOM-EXT-1BAF14-v1.0.0 name: strings.py date: 2026-06-08 ====
def snake_to_title(s: str) -> str:
    """Convert snake_case string to Title Case."""
    return s.replace("_", " ").title()
