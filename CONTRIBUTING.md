# Contributing

This repository follows [GitHub Flow](https://docs.github.com/en/get-started/using-github/github-flow)
and [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).

## Before you start

- Do not invent benchmark numbers, inject noise into results, or retune
  a frozen policy (`configs/experiment.yaml`, `configs/experiment_v2.yaml`)
  after looking at that campaign's holdout.
- Do not add a profiler UI, dashboard, or LLM "auto diagnosis".
- Real application evidence lives under `artifacts/` and is not in git.
  Reproduce with `experiments/README.md` on a machine you control.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/python -m unittest discover -s tests -v
```

Parser and rule tests use in-repo fixtures only. They are not performance evidence.

## Branches

Create a branch from `main`:

| Prefix | Use |
|---|---|
| `feat/<topic>` | user-visible behavior |
| `fix/<topic>` | bug fix |
| `docs/<topic>` | documentation only |
| `test/<topic>` | tests only |
| `chore/<topic>` | tooling, CI, templates |
| `ci/<topic>` | workflow changes |

Examples: `feat/cloudsuite-parser`, `fix/zero-denominator`, `docs/limitations`.

## Commits

```
<type>(<optional scope>): <imperative summary>
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`.

- One concern per commit. A reviewer should be able to revert a commit safely.
- Explain *why* in the body when the diff is not obvious.
- Do not bundle unrelated files so the commit "looks complete".

## Pull requests

1. Open an issue for behavior or policy changes when practical.
2. Push the branch and open a PR against `main` using the PR template.
3. Keep the PR scoped to one topic. Prefer several small PRs over one mixed PR.
4. CI (`unittest`) must pass. Hardware `perf` runs are not required for merge.

## Issues

Use the issue forms under `.github/ISSUE_TEMPLATE/`. Measurement questions
that need raw `perf` output should attach a redacted run directory listing and
`run.json` quality block, not host secrets.
