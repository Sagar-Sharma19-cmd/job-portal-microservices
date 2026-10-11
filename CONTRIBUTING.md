# Contributing — Team 16

These rules keep five people from breaking each other's code. Please follow them from the first commit.

## Branches

| Branch | Purpose | Who pushes |
| --- | --- | --- |
| `main` | Demo-ready, tagged releases only | Nobody directly. Lead merges from `develop` |
| `develop` | Integration branch; everything merges here first | Nobody directly. Only through pull requests |
| `feature/<service>-<what>` | New work | You |
| `fix/<service>-<what>` | Bug fixes | You |
| `docs/<what>` | Documentation only | You |

Examples: `feature/job-reservations`, `feature/gateway-routing`, `fix/application-saga-timeout`,
`docs/api-contracts`.

## Daily workflow

```bash
git checkout develop
git pull origin develop
git checkout -b feature/candidate-crud      # one branch per task

# ...work, commit small and often...
git add candidate-service/
git commit -m "feat(candidate): add create and get candidate APIs"

git fetch origin
git rebase origin/develop                   # stay up to date before pushing
git push -u origin feature/candidate-crud
```

Then open a pull request on GitHub: **base = `develop`**, compare = your branch.

## Commit messages

Format: `type(scope): short description` in present tense, lowercase, no full stop.

| Type | Use for |
| --- | --- |
| `feat` | New feature or endpoint |
| `fix` | Bug fix |
| `test` | Adding or changing tests |
| `docs` | Documentation only |
| `refactor` | Code change with no behaviour change |
| `chore` | Setup, config, dependencies |

Scopes: `gateway`, `registry`, `common`, `candidate`, `job`, `application`, `recruitment`,
`notification`, `docs`, `postman`, `scripts`.

Examples:

```
feat(job): add v2 job response with structured salary
fix(gateway): return 504 when a service times out
test(application): cover saga compensation when recruitment is down
docs(architecture): update saga diagram
```

## Pull request checklist

Your PR is reviewed against this list. Tick it in the PR description.

- [ ] Branch is rebased on the latest `develop`
- [ ] Service starts without errors and `/docs` (Swagger) loads
- [ ] `GET /health` returns `UP`
- [ ] Endpoints match `docs/api-contracts.md` exactly (paths, fields, status codes, error format)
- [ ] Your Postman requests for this change pass
- [ ] No `.db`, `.env`, `venv/` or `__pycache__/` files committed
- [ ] No hard-coded URLs like `http://localhost:8002` for other services. Use the discovery client
- [ ] Your service does not open another service's database

## Hard rules (these block a merge)

1. **Never access another service's database.** If you need its data, call its API.
2. **API contracts are frozen.** To change a request, response or status code, first open a PR that edits
   `docs/api-contracts.md`, and tell the people who call your API in the group.
3. **Changes to `common/` need a message in the group**, because every service uses it.
4. **Don't merge your own PR.** The lead reviews; Sai also reviews `common/` changes.

## Merge conflicts

Whoever opens the PR resolves the conflict on their own branch:

```bash
git fetch origin
git rebase origin/develop
# fix the conflicted files, then:
git add <files>
git rebase --continue
git push --force-with-lease
```

If you are stuck, post the error in the group. Don't delete the branch or force-push to `develop`.

## Releases

The lead merges `develop` into `main` at each milestone and tags it:
`v0.1-services`, `v0.2-integration`, `v0.3-saga`, `v1.0-demo`.
