# Demo cases

Small PDFs for trying Paste Guard by hand. They belong to the fictional company Calloway Metrics, whose
confidential documents are indexed from `demo/company-docs/`. Paste their text into claude.ai or chatgpt.com,
or drop the PDF itself into the chat box, with the backend running and the extension loaded.

| File | Expected verdict | Why |
|---|---|---|
| Strategy Notes Sep 2026.pdf | block | Verbatim excerpt of the Ferrolake acquisition board memo |
| Platform Roadmap Sync.pdf | block | The same memo reworded as a casual deal summary |
| Analytics Client Setup.pdf | block | Contains a fake Anthropic API key |
| API Client Helpers.pdf | block | Contains a fake Stripe key. Only the key is redacted; the rest of the code is ordinary |
| Customer Feedback Summary.pdf | nudge | Two loose sentences that touch on the memo's topic without its details |
| Office Kitchen Guide.pdf | allow | Unrelated office notice |

Two more cases are part of the demo script but are not in this folder yet:

| File | Expected verdict | Why |
|---|---|---|
| Signing Module Review.pdf | coach when pasted | Code close to the indexed sample repository. Known gap: dropped as a file it does not get the same verdict |
| Team Lunch Ideas.pdf | allow | Unrelated text |

All keys in these files are fake and do not work.
