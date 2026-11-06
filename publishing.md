Getting 1.0.8 onto PyPI

1. One-time setup (skip any part you've already done):
- PyPI: open https://pypi.org/manage/project/dStats/settings/publishing/ and add a GitHub publisher with owner Arifcse21, repository dStats, workflow release.yml, environment pypi.
- GitHub: go to repo Settings → Environments → New environment and name it pypi.

2. Do a trial run on main first: Actions → release → Run workflow → Branch: main. This builds everything, including the fixed macOS job, and runs both audits without publishing. Wait for all green, and look at the artifacts if you like.

3. Tag and push:
git tag v1.0.8
git push origin v1.0.8
This run builds again, checks that the tag matches version = "1.0.8" in pyproject.toml, uploads all 8 files to PyPI, and creates the GitHub Release. A few minutes after it goes green, https://pypi.org/project/dStats/ shows 1.0.8.
