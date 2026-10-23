1. Download and extract this ZIP anywhere (e.g. Downloads).
2. Right-click in the extracted folder > Open in Terminal (PowerShell).
3. Run: powershell -ExecutionPolicy Bypass -File .\apply_both.ps1
   This clones the public discharge-letter-check repo beside your AfterWard folder if absent.
4. Review the diffs printed. No commits/pushes occur.
5. Main repo: git status --short; git add README.md docs/REPOSITORY_GUIDE.md; git commit -m "docs: improve judging navigation"; git push origin main
6. Package repo: cd C:\Users\shilp\discharge-letter-check; git add README.md; git commit -m "docs: link AfterWard and clarify release status"; git push origin main
Video and Devpost placeholders are intentionally untouched.
