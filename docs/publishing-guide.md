# Automated Release & Publishing Guide

## Overview

Your project is now set up with **semantic versioning** and **automated PyPI publishing** using:

- **python-semantic-release**: Analyzes commit history and automatically bumps versions (Python native)
- **commitizen**: Validates conventional commit format locally before commits
- **pre-commit**: Git hooks framework for enforcing quality standards on every commit
- **GitHub Actions**: Three workflows handle testing, linting, and publishing
- **Conventional Commits**: Your commit messages determine version bumps

### Important: Configuration Clarification

The project uses **Python native tools** for automation:
- Configuration is in `pyproject.toml` under `[tool.semantic_release]` and `[tool.commitizen]`
- **`.releaserc.json` is NOT used** — that's for the Node.js `semantic-release` package
- The `.pre-commit-config.yaml` configures git hooks to run quality checks locally

## Quick Start

### 1. Initial Setup (Required)

#### PyPI Trusted Publisher (OIDC)

This project uses [Trusted Publishers](https://docs.pypi.org/trusted-publishers/)
(OpenID Connect) instead of API tokens. No secrets need to be stored in GitHub —
PyPI verifies the identity of the GitHub Actions workflow directly.

**For a brand-new project** (not yet on PyPI):

1. Log in to [PyPI](https://pypi.org/) and go to your account's
   [Publishing](https://pypi.org/manage/account/publishing/) page.
2. Under "Add a new pending publisher", fill in:
   - **PyPI project name**: `zencontrol-cloud-mcp`
   - **Owner**: `oWretch`
   - **Repository name**: `zencontrol-cloud-mcp`
   - **Workflow name**: `release.yml`
   - **Environment name**: `pypi`
3. Click **Add**.

**For an existing project** (already on PyPI):

1. Go to the project's [Publishing settings](https://pypi.org/manage/project/zencontrol-cloud-mcp/settings/publishing/).
2. Add the same GitHub publisher details as above.

See [Creating a project through OIDC](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
for full details.

#### GitHub Environment

The release workflow requires a GitHub Actions environment named `pypi`:

1. Go to **Settings → Environments → New environment**.
2. Name it `pypi`.
3. Optionally add deployment protection rules (e.g., required reviewers).

#### Pre-commit Hooks

```bash
# Install pre-commit hooks (local development)
uv run pre-commit install --hook-type commit-msg --hook-type pre-commit
```

### 2. Making Commits (Ongoing)

Use conventional commit format:

```bash
# Bug fix (patch: 1.0.0 → 1.0.1)
git commit -m "fix: resolve lighting control timeout issue"

# New feature (minor: 1.0.0 → 1.1.0)
git commit -m "feat: add colour temperature control"

# Breaking change (major: 1.0.0 → 2.0.0)
git commit -m "feat!: redesign API for better performance"
```

### 3. Publishing (Automatic!)

When you merge to `main`:
1. ✅ Tests run automatically
2. ✅ If tests pass, semantic-release analyzes commits
3. ✅ Version is bumped (major/minor/patch)
4. ✅ CHANGELOG is generated
5. ✅ Package is published to PyPI
6. ✅ Release tag is created on GitHub

## Workflows

### test.yml
- Runs on: Every push and pull request
- Tests Python 3.11 and 3.12
- Checks linting and formatting
- **Blocks merge if tests fail**

### release.yml
- Runs on: Merge to `main` branch only
- Semantic-release analyzes commits
- Updates version in code
- Publishes to PyPI via OIDC Trusted Publisher (no API token needed)
- **Creates GitHub release with auto-generated changelog**
- **Tags are immutable once created**

### commit-lint.yml
- Runs on: Every pull request to `main`
- Validates commit messages follow conventional commits format
- **Blocks merge if format is invalid**

## Commit Message Examples

| Commit Message | Version Change | Release Notes |
|---|---|---|
| `fix: resolve OAuth timeout` | 0.1.0 → 0.1.1 | Bug fixes |
| `feat: add live sensor readings` | 0.1.0 → 0.2.0 | Features |
| `feat!: redesign config schema` | 0.1.0 → 1.0.0 | Breaking |
| `docs: update README` | 0.1.0 (no change) | — |

**Format**: `type(scope): message`
- `type`: `feat`, `fix`, `docs`, `chore`, `refactor`, `perf`, `test`
- `scope`: optional, e.g., `auth`, `api`, `deps`, `release`, `tests`
- `message`: clear, lowercase

Breaking changes use `!` or include `BREAKING CHANGE:` in body.

The automated version bump commit uses `chore(release): {version}` as the subject line
and includes the configured body from `pyproject.toml`, so it remains valid under
commit linting. The release workflow skips re-running on automated release commits
by checking for the `chore(release):` prefix.

## Troubleshooting

### Workflow doesn't run
- Check: Is the Trusted Publisher configured on PyPI? (see Initial Setup above)
- Check: Does the GitHub `pypi` environment exist? (Settings → Environments)
- Check: Did you merge to `main` branch?
- Check: Did previous commits follow conventional format?

### Version didn't bump
- Ensure commit message format: `feat:`, `fix:`, `feat!:`
- Check workflow logs: Actions tab → release.yml

### Can't push to protected branch
- The workflow uses GitHub Actions token, which can push
- If manually pushing fails, check branch protection settings

### PyPI upload failed
- Verify the Trusted Publisher is configured correctly on PyPI
- Ensure the workflow name (`release.yml`) and environment (`pypi`) match exactly
- Check `id-token: write` permission is set in the workflow
- See [Troubleshooting Trusted Publishers](https://docs.pypi.org/trusted-publishers/troubleshooting/)

## Files Changed

- `pyproject.toml` - Added metadata, classifiers, semantic-release config
- `.github/workflows/test.yml` - CI/CD for testing
- `.github/workflows/release.yml` - Automated release workflow
- `.releaserc.json` - Semantic-release configuration
- `src/zencontrol_cloud_mcp/__init__.py` - Already had `__version__`
- `docs/release-checklist.md` - Detailed pre-publishing checklist

## Testing the Workflow Locally

```bash
# Install dev dependencies
uv sync

# See what version would be released
uv run semantic-release version --no-push --dry-run

# Build distribution
uv run python -m build

# Check built artifacts
ls -lh dist/
```

## Next Steps

1. ✅ Configure [Trusted Publisher on PyPI](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/) (OIDC — no API token needed)
2. ✅ Create `pypi` environment in GitHub (Settings → Environments)
3. ✅ Install pre-commit hooks locally: `uv run pre-commit install --hook-type commit-msg --hook-type pre-commit`
4. ✅ **Enable immutable releases**: Settings → Releases → check "Enable release immutability"
5. ✅ Make a test commit with `feat:` prefix
6. ✅ Merge to `main` and watch the workflow run
7. ✅ Verify release on [PyPI](https://pypi.org/project/zencontrol-cloud-mcp/)
8. ✅ Check GitHub release shows 🔒 **Immutable** label

## GitHub Release & Tag Immutability

**GitHub's Immutable Releases Feature** (2024+):

This project's workflow uses GitHub's native immutable releases for supply chain security:

### What Gets Protected
- ✅ **Git tags** — Locked to specific commit, cannot be moved or reused
- ✅ **Release assets** — Binary files cannot be modified or deleted
- ✅ **Release attestation** — Cryptographically verifiable record auto-generated
- ✅ **Repository resurrection attacks** — Cannot reuse tags even if repo is deleted

### How to Enable

1. Repository Settings → Releases section
2. Check **"Enable release immutability"** ✅
3. Note: Only applies to future releases (not retroactive)

### Release Publication Workflow

The automation follows GitHub's best practice for immutable releases:

1. **Create draft** — Release created with auto-generated notes
2. **Attach assets** — PyPI package files added while draft
3. **Publish** — Release becomes immutable (final state)

This ensures all assets are present before immutability takes effect.

### Verification

When a release is immutable, you'll see a 🔒 **Immutable** label on the GitHub release page. Users can verify:
- Release integrity via release attestation
- Asset signatures haven't changed
- Tag is locked to original commit

**To prevent accidental deletion:**
1. Settings → Branches → Add rule for main
2. Enable "Restrict who can push to matching branches" (admins only)
3. Consider organization-wide immutable releases policy (Settings → Repository → Releases)

See [release-checklist.md](release-checklist.md) for the complete pre-publishing checklist.
