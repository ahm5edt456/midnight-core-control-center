# v1.0.0 release checklist

1. Install Stage 12 and run automated preflight:
   `python3 scripts/release_suite.py check --project .`
2. Review `dist/QA_REPORT.md`, and fix every `FAIL`.
3. Complete `docs/TEST_PLAN.md` on Fedora 45/GNOME. Do not claim all features verified until they have actually been exercised.
4. Review sensitive data: `git status --short`, `git ls-files`, `git log --all --name-only`, and search for credentials. Scan current sources AND history; if any key was committed, rotate it and remove it properly from history.
5. Add a chosen `LICENSE` if publishing as open source. Don't assume a license is automatic.
6. Update public `README.md` using `docs/README_PUBLIC_TEMPLATE.md` as a guide; do not overwrite your existing README blindly.
7. Check `git diff --check` and `git diff --cached --check`; commit reviewed changes.
8. Run `python3 scripts/release_suite.py build --project .`. Verify:
   `cd dist && sha256sum -c midnight-core-control-center-v1.0.0-source.zip.sha256`
9. Inspect archive:
   `unzip -l dist/midnight-core-control-center-v1.0.0-source.zip | less`
10. Push repository to GitHub explicitly **only after** all steps above succeed.
11. Tag `v1.0.0` **only** after manual GUI testing. Push annotated tag and publish source archive/checksum with reviewed release notes.

Example commands (run from the project root; **publishes only when you execute them**):

```bash
gh auth status
git remote -v
# If no origin exists:
gh repo create midnight-core-control-center --public --source=. --remote=origin --push
# If origin exists, verify its destination and push there instead:
# git push -u origin main

git tag -a v1.0.0 -m "Midnight Core Control Center v1.0.0"
git push origin v1.0.0
gh release create v1.0.0 \
  dist/midnight-core-control-center-v1.0.0-source.zip \
  dist/midnight-core-control-center-v1.0.0-source.zip.sha256 \
  --title "Midnight Core Control Center v1.0.0" \
  --notes-file docs/RELEASE_NOTES_v1.0.0.md \
  --verify-tag
```

If an `origin` remote already exists, **do not** run `gh repo create` blindly. Check which account and repo it points to. Never place backup ZIPs, `.env`, or personal diagnostic logs in the repo or release assets.
