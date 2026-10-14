import markdown, pathlib
src = pathlib.Path(__file__).with_name("paste-guard-writeup.md")
body = markdown.markdown(src.read_text(), extensions=["tables", "fenced_code", "attr_list", "md_in_html"])
css = """
@page { size: Letter; margin: 0.75in 0.8in; @bottom-right { content: counter(page); } }
body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 10.5pt; line-height: 1.5; color: #1f2933; }
h1 { font-size: 30pt; margin: 0 0 4px; color: #102a43; letter-spacing: -0.5px; }
.subtitle { font-size: 13pt; color: #334e68; margin: 0 0 10px; }
.meta { font-size: 9.5pt; color: #627d98; margin: 0 0 14px; }
.note { background: #fff8e6; border-left: 4px solid #f0b429; padding: 8px 12px; font-size: 10pt; margin-bottom: 8px; }
h2 { font-size: 15pt; color: #102a43; border-bottom: 2px solid #d9e2ec; padding-bottom: 3px; margin-top: 22px; break-after: avoid; }
p, li { orphans: 2; widows: 2; }
table { border-collapse: collapse; width: 100%; margin: 10px 0 14px; font-size: 9pt; }
tr { break-inside: avoid; }
th { background: #243b53; color: #fff; text-align: left; padding: 5px 6px; }
td { padding: 4px 6px; border-bottom: 1px solid #d9e2ec; }
tr:nth-child(even) td { background: #f5f7fa; }
img { display: block; max-width: 100%; max-height: 3.2in; margin: 8px auto 2px; }
img + em, .cap { display:block; }
code { font-family: Menlo, Consolas, monospace; font-size: 8.8pt; background: #f0f4f8; padding: 1px 3px; border-radius: 3px; }
.sources { font-size: 8.5pt; color: #627d98; margin-top: 20px; border-top: 1px solid #d9e2ec; padding-top: 6px; }
"""
# add captions under images from alt text
import re
body = re.sub(r'<p><img alt="([^"]*)" src="([^"]*)" /></p>',
              r'<figure style="break-inside:avoid;margin:10px 0"><img alt="\1" src="\2" /><figcaption style="text-align:center;font-size:8.8pt;color:#627d98">\1</figcaption></figure>', body)
html = f"<!doctype html><html><head><meta charset='utf-8'><title>Paste Guard write-up</title><style>{css}</style></head><body>{body}</body></html>"
src.with_suffix(".html").write_text(html)
