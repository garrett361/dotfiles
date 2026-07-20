# dotfiles

Set `export NVIM_APPNAME=nvim_min` to use the minimal nvim config.

`git-tree`, my stacked-branch / cascading-rebase CLI, lives in its own repo:
<https://github.com/garrett361/git_tree>. `get_deps.sh` clones it as a sibling of this repo and
`install.sh` installs it as an editable `uv` tool (auto-discovered by git as `git tree`).
