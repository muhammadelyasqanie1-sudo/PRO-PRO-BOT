"""Check the embedded Mini App JavaScript parses successfully with Node.js."""
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import tempfile


class InlineScripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.capture = False
        self.current = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "script" and not dict(attrs).get("src"):
            self.capture = True
            self.current = []

    def handle_data(self, data):
        if self.capture:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self.capture:
            self.scripts.append("".join(self.current))
            self.capture = False
            self.current = []


def main():
    html = Path(__file__).resolve().parent.parent / "webapp" / "index.html"
    parser = InlineScripts()
    parser.feed(html.read_text(encoding="utf-8"))
    assert parser.scripts, "No inline Mini App script was found."
    script = parser.scripts[-1]
    with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as f:
        f.write(script)
        path = f.name
    result = subprocess.run(["node", "--check", path], capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    print("miniapp frontend syntax test passed")


if __name__ == "__main__":
    main()
