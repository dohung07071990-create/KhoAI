from pathlib import Path
import re


def test_all_css_custom_properties_are_defined():
    css_dir = Path(__file__).resolve().parents[1] / "frontend"
    css_files = sorted(css_dir.glob("*.css"))
    assert css_files, "No frontend CSS files found"

    css = "\n".join(path.read_text(encoding="utf-8") for path in css_files)
    defined = set(re.findall(r"--([\w-]+)\s*:", css))
    referenced = set(re.findall(r"var\(\s*--([\w-]+)", css))
    missing = sorted(referenced - defined)

    assert not missing, f"Undefined CSS custom properties: {missing}"
