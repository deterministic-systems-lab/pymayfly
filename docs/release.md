# Release Process

pymayfly is published to PyPI from GitHub Actions using **Trusted Publishing**
(OIDC). No long-lived PyPI API tokens are stored anywhere — GitHub mints a
short-lived identity token for each run and PyPI verifies it against the
registered publisher. The trusted publishers and the `pypi` / `testpypi` GitHub
Environments are already configured; this document covers cutting a release.

The release workflow lives in
[`.github/workflows/release.yml`](../.github/workflows/release.yml). It is
triggered by pushing a tag of the form `v*` and runs three stages:

1. **test** — the same lint / type-check / test matrix as CI (Python 3.11 and
   3.12). Publishing cannot proceed unless this is green.
2. **build** — verifies the tag matches `pyproject.toml`'s version, builds the
   sdist and wheel, and runs `twine check`.
3. **publish** — uploads via OIDC. A final tag (e.g. `v0.2.0`) publishes to
   **PyPI**; a pre-release tag (e.g. `v0.2.0rc1`, `v0.2.0b1`, `v0.2.0a1`,
   `v0.2.0.dev1`) publishes to **TestPyPI** so a release can be rehearsed
   end-to-end first.

## Cutting a release

### 1. Pre-flight checks (local)

Start from a clean, up-to-date `main` and confirm the exact gates the workflow
will run, plus a local build, so you find problems before tagging:

```bash
git checkout main
git pull --ff-only

python -m ruff check pymayfly tests
python -m mypy pymayfly
python -m pytest tests/unit tests/integration -v --cov=pymayfly --cov-report=term-missing

# dry-run the artifacts the build stage produces
rm -rf dist
python -m build
python -m twine check dist/*
```

If any of these fail, fix them on `main` (via PR) before continuing — a tag that
fails CI never publishes, but catching it locally avoids a wasted tag.

### 2. Bump the version

Edit `project.version` in `pyproject.toml`. Use [PEP 440](https://peps.python.org/pep-0440/)
versions and [semantic versioning](https://semver.org/) intent:

- Bug fixes → patch (`0.1.0` → `0.1.1`)
- New, backward-compatible features → minor (`0.1.0` → `0.2.0`)
- Breaking changes → major (`0.x` → `1.0.0`)
- Rehearsal / preview → pre-release suffix (`0.2.0rc1`, `0.2.0b1`, `0.2.0.dev1`)

The tag you push later must equal this value (PEP 440-normalized) or the build
stage fails fast.

### 3. Update the changelog

In `CHANGELOG.md`, rename the `[Unreleased]` heading to the new version with
today's date, and open a fresh empty `[Unreleased]` section above it:

```markdown
## [Unreleased]

## [0.2.0] - 2026-06-01

### Added
- ...
```

Confirm the entries accurately describe what shipped (new providers, behavior
changes, fixes) so the changelog matches the artifacts.

### 4. Merge to main

Open a PR with the version bump and changelog update, get CI green, and merge to
`main`. The release must be cut from a commit that is on `main`.

### 5. Tag and push

Tag the merged commit and push the tag. Use an annotated tag so the release
carries a message:

```bash
git checkout main
git pull --ff-only
git tag -a v0.2.0 -m "pymayfly 0.2.0"
git push origin v0.2.0
```

Pushing the tag is what triggers the **Release** workflow. (To rehearse instead,
push a pre-release tag — see [Rehearsing on TestPyPI](#rehearsing-on-testpypi).)

### 6. Monitor and approve

Open the **Actions** tab and watch the **Release** run. If the `pypi`
environment has a required reviewer configured, approve the deployment when the
`publish-pypi` job pauses for it. The run is green once the artifacts are
uploaded.

### 7. Verify the published release

Confirm the release is installable and correct from a clean environment:

```bash
python -m venv /tmp/pymayfly-verify
/tmp/pymayfly-verify/bin/pip install "pymayfly==0.2.0"
/tmp/pymayfly-verify/bin/python -c "import pymayfly; print(pymayfly.__version__)"
```

Then check the project page on <https://pypi.org/project/pymayfly/> shows the new
version, the correct description, and both the wheel and sdist under "Download
files".

### 8. Publish release notes (optional)

Create a GitHub Release for the tag (**Releases → Draft a new release →** select
`v0.2.0`) and paste the changelog section for this version. This gives the tag
human-readable notes and a discoverable download page.

## Rehearsing on TestPyPI

To validate the full pipeline without shipping to production PyPI, tag a
pre-release:

```bash
git tag -a v0.2.0rc1 -m "pymayfly 0.2.0rc1"
git push origin v0.2.0rc1
```

This routes the build to TestPyPI. Install and smoke-test it with:

```bash
pip install --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ pymayfly==0.2.0rc1
```

The `--extra-index-url` lets dependencies resolve from real PyPI while the
pymayfly pre-release comes from TestPyPI. Once a release candidate looks good,
bump to the final version and tag it (e.g. `v0.2.0`) to publish to PyPI.

## Notes

- The tag must match `pyproject.toml`'s version (compared with PEP 440
  normalization); a mismatch fails the build stage before anything is uploaded.
- PyPI does not allow re-uploading a version that already exists. If a release is
  broken, bump to a new version (e.g. `0.2.1`) and release again — you cannot
  overwrite `0.2.0`.
- If the workflow fails in the **test** or **build** stage, nothing is published;
  fix the cause on `main`, delete the tag (`git push origin :v0.2.0`), and re-tag.
- Yanking a bad-but-published release is done from the PyPI web UI.
