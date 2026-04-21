# Configuration Reference

## GitHub's Immutable Releases (2024+)

This project uses GitHub's native **immutable releases** feature for supply chain security.

### What It Does

Once enabled in repository settings, all future releases become immutable:
- 🔒 Git tags cannot be moved, changed, or reused
- 🔒 Release assets (wheels, tarballs) are write-protected
- 🔒 Automatic release attestation for verification
- 🔒 Prevents supply chain attacks and tampering

### How to Enable

1. **Repository Settings** → Scroll to "Releases"
2. Check **"Enable release immutability"**
3. Click Save
4. ⚠️ Only applies to releases created **after** enabling

### Release Publication Flow

The workflow follows GitHub's best practice:

```
semantic-release detects version bump
    ↓
Creates draft release (can still modify)
    ↓
Attaches PyPI artifacts
    ↓
Publishes draft → becomes immutable 🔒
    ↓
Release is now permanent and tamper-proof
```

### Verification

Users can verify release integrity:
```bash
# Check attestation
gh release view v0.2.0 --json attestations

# Verify signature
gh release download v0.2.0 --clobber
gh attestation verify dist/*.whl --format short
```

See [Verifying the integrity of a release](https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/verifying-the-integrity-of-a-release) for details.

### Workflow Implementation

The `release.yml` workflow:
1. Creates release as **draft** with `--draft` flag
2. Attaches all distribution files
3. Publishes with `gh release edit --draft=false --latest`

This ensures complete assets before immutability takes effect.

---

## semantic-release Versions

This project uses **python-semantic-release** (Python native), not the Node.js `semantic-release` package.

### File Organization

| File | Purpose | Tool |
|------|---------|------|
| `pyproject.toml` `[tool.semantic_release]` | Version bumping config | `python-semantic-release` |
| `pyproject.toml` `[tool.commitizen]` | Conventional commit tracking | `commitizen` |
| `.pre-commit-config.yaml` | Git hooks for quality checks | `pre-commit` framework |
| `pyproject.toml` `[tool.ruff]` | Code linting & formatting | `ruff` |
| `.github/workflows/test.yml` | CI for tests & linting | GitHub Actions |
| `.github/workflows/release.yml` | Automated releases to PyPI | GitHub Actions |
| `.github/workflows/commit-lint.yml` | PR commit validation | GitHub Actions |

### ❌ Unused Files

- **`.releaserc.json`** — This is for Node.js `semantic-release` and is NOT used by this project. You can delete it.

## Tool Purposes

### python-semantic-release
- **What:** Analyzes commit history and automatically bumps versions
- **Config:** `pyproject.toml` → `[tool.semantic_release]`
- **Scans:** Conventional commit messages (via Angular parser)
- **Actions:** Updates version, generates changelog, creates git tags, publishes to PyPI

### commitizen
- **What:** Interactive commit message builder & validator
- **Config:** `pyproject.toml` → `[tool.commitizen]`
- **Used for:** Local `git cz commit` workflow (optional) or pre-commit validation

### pre-commit
- **What:** Git hooks framework (runs checks before commits)
- **Config:** `.pre-commit-config.yaml`
- **Hooks included:**
  - Conventional commit validation (via `compilerla/conventional-pre-commit`)
  - Ruff linting & formatting
  - YAML/JSON formatting
  - Trailing whitespace, EOF fixes
  - Secret scanning with `detect-secrets`

### ruff
- **What:** Python linter & formatter (all-in-one)
- **Config:** `pyproject.toml` → `[tool.ruff]`
- **Replaces:** Black, isort, pylint, flake8

## Workflow Execution

### 1. Local Development

```bash
# Pre-commit hooks run on every git commit
git commit -m "feat: add new feature"
# ✅ Runs: conventional-commit check, ruff lint/format, yaml validation, etc.

# Or build/test manually
uv run pytest
uv run ruff check src/
uv run ruff format src/
```

### 2. Pull Request to main

GitHub Actions runs:
- **test.yml** → pytest + ruff checks (must pass)
- **commit-lint.yml** → Validates PR commits follow conventional format

### 3. Merge to main

GitHub Actions runs:
- **release.yml** → Automatically:
  1. Analyzes commit history
  2. Bumps version in code
  3. Generates `CHANGELOG.md`
  4. Pushes tags to GitHub
  5. Publishes to PyPI
  6. Creates immutable GitHub Release

## Configuration Details

### Angular Commit Parser

`python-semantic-release` uses the "Angular" parser (compatible with Conventional Commits):
- `fix:` → patch bump
- `feat:` → minor bump
- `BREAKING CHANGE:` or `feat!:` → major bump
- `docs:`, `chore:`, `test:`, etc. → no bump

This is configured in `pyproject.toml`:
```toml
[tool.semantic_release]
commit_parser = "semantic_release.history.angular_parser"
parser_angular_patch_types = ["fix", "perf"]
parser_angular_minor_types = ["feat"]
```

### Pre-commit Scope Allowlist

Commits must use one of these scopes (optional):
```
auth, api, tools, models, scope, resources, dev, docs, chore, ci, deps, release, tests
```

Defined in `.pre-commit-config.yaml`:
```yaml
args:
  - --scopes
  - auth,api,tools,models,scope,resources,dev,docs,chore,ci,deps,release,tests
```

### semantic-release Commit Message

Release commits are generated with a conventional commit message so they pass the
same validation rules as normal development commits.

The exact `commit_message` value is defined in `pyproject.toml` and should be
treated as the source of truth for the release commit body.

## Customization

### Adding/Removing Release Types

Edit `pyproject.toml`:
```toml
[tool.semantic_release.commit_parser_options]
major_on_keyword = ["BREAKING CHANGE", "BREAKING"]
```

### Changing Scopes

Update in two places:
1. `.pre-commit-config.yaml` → `--scopes ...`
2. `.github/workflows/commit-lint.yml` → CI commit validation allowlist
3. `CONTRIBUTING.md` → Scope list for documentation

### Disabling Hooks

```bash
# Skip pre-commit hooks (not recommended)
git commit --no-verify

# Skip a specific hook type
git commit -m "..." --no-verify --no-verify-hook pre-commit
```

## Troubleshooting

### Pre-commit hooks fail on first commit

Pre-commit downloads and caches hook environments on first run:
```bash
# This is normal; retry the commit
git commit -m "feat: ..."

# Or manually update cache
pre-commit run --all-files
```

### Commit message rejected by conventional-pre-commit

Your message doesn't follow conventional format. Use:
```bash
# Correct format
git commit -m "feat(scope): description"

# NOT
git commit -m "implement new feature"
```

### Release workflow didn't run

Check:
1. Did you merge to `main` branch?
2. Do commits follow conventional format?
3. Check Actions tab → release.yml logs

### CHANGELOG.md not generated

`python-semantic-release` only generates changelog if:
- Commits follow conventional format
- Version was bumped
- Check: `changelog_file = "CHANGELOG.md"` in `pyproject.toml`

### Immutable release not published

Check:
1. Is "Enable release immutability" checked in Settings → Releases?
2. Did the workflow create a draft release?
3. Check Actions tab → release.yml → "Publish immutable release" step

## References

- [python-semantic-release docs](https://python-semantic-release.readthedocs.io/)
- [GitHub Immutable Releases](https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/immutable-releases)
- [Preventing Changes to Your Releases](https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/preventing-changes-to-your-releases)
- [Verifying Release Integrity](https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/verifying-the-integrity-of-a-release)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [pre-commit docs](https://pre-commit.com/)
- [Ruff docs](https://docs.astral.sh/ruff/)
