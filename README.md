### LinkedIn Posts Extractor

Python CLI script to extract recent posts from a LinkedIn profile using Playwright.

---

## Commands

| Step | Description             | Command                       |
|------|-------------------------|-------------------------------|
| 1    | Install dependencies    | `uv sync`                     |
| 2    | Run the script          | `uv run python main.py`       |

---

## Notes

- Browser context is stored in `_ctx.json` for session reuse.  
- Results are saved in `results.json`.  
- Logs progress in console with `time - LEVEL - message` format.  