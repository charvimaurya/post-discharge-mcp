# Apply AfterWard judging documentation safely

1. Copy `docs/judging-guide.md` into your local repository's `docs` folder.
2. Copy `scripts/apply_readme_judging_update.py` into the local repository's `scripts` folder.
3. From `C:\Users\shilp\AfterWard-A-Living-Recovery-Plan-for-Alexa`, run:
   ```powershell
   python scripts/apply_readme_judging_update.py
   git diff -- README.md
   git status --short
   ```
4. Compare the guide with the **latest checkout**, especially Alexa docs paths, the synthetic fixture filename, commands and tool counts. Update anything stale; do not blindly commit.
5. Add actual video and Devpost URLs once published (the script intentionally does not invent them).
6. Run tests and smoke checks in your own configured environment. Never run reset or ingest commands against shared data without approval.
7. If satisfied:
   ```powershell
   git add README.md docs/judging-guide.md scripts/apply_readme_judging_update.py
   git commit -m "docs: add reproducible hackathon judging guide"
   git push origin main
   ```

No AWS deployment or application code changes are included. Nothing has been pushed by ChatGPT.
