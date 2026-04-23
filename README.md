# dotfiles

Set `export NVIM_APPNAME=nvim_min` to use the minimal nvim config.

## Gitstack

[gitstack](https://github.com/garrett361/gitstack) is a lightweight tool for stacking branches
and GitHub PRs. It lives as a git submodule at `gitstack/`.

`install.sh` symlinks `gitstack/gitstack.py` → `~/.local/share/gitstack.py` and registers a
`git stack` alias. `get_deps.sh` initializes the submodule automatically. After a fresh clone,
run both scripts and use `git stack -h` to verify.

### Pulling upstream changes

```bash
git submodule update --remote gitstack   # fetch latest main from fork
git add gitstack
git commit -m "chore(gitstack): update submodule"
```

### Dev workflow

```bash
cd gitstack
git checkout main          # submodule starts detached — check out a branch first
# edit gitstack.py, etc.
git commit -am "feat: ..."
git push
cd ..
git add gitstack
git commit -m "chore(gitstack): update submodule pointer"
```

Changes pushed to `garrett361/gitstack` are immediately available to anyone who runs
`git submodule update --remote gitstack` in the dotfiles repo.
