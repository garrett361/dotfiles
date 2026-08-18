# dotfiles

Setup:

```
# Install dependencies
./get_deps.sh 

# Set up symlinks and other installation steps
./install.sh
```

## Notes

Set `export NVIM_APPNAME=nvim_min` to use the minimal nvim config.

`git-tree`, my stacked-branch / cascading-rebase CLI, lives in its own repo:
<https://github.com/garrett361/git_tree>. `get_deps.sh` clones it as a sibling of this repo and
`install.sh` installs it as an editable `uv` tool (auto-discovered by git as `git tree`).

## SSH key via 1Password

1Password holds the ssh key and answers authentication requests over a socket. The private half
never leaves the vault, so no machine needs a key file on disk.

On the mac, once: turn on "Use the SSH agent" in 1Password, add the public key to GitHub as an
authentication key, and create `~/.ssh/config` (machine-local, not installed by `install.sh`) with

```
Host *
  IdentityAgent "~/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock"
```

`ssh -T git@github.com` should then greet you by username.

To use a new remote machine:

1. Add the public key to `~/.ssh/authorized_keys` on the host, or hand it to the provider at
   provision time. To get the key text, copy it from the 1Password item or run `ssh-add -L` on the
   mac, which prints every key the agent holds.
2. Give the host an entry in `~/.ssh/config` on the mac, above the `Host *` block, since ssh keeps
   the first value it finds for each keyword:

   ```
   Host cluster1
     HostName <address>
     User <user>
     ForwardAgent yes
   ```

   Forward only to hosts you trust, never under `Host *`. Forwarding puts a socket on the remote
   host that anything running as you, or as root, can use to authenticate as you until you
   disconnect. It cannot read the key itself.
3. Clone this repo there over ssh, `git clone git@github.com:garrett361/dotfiles.git`, and run
   `./install.sh`, which installs the shell profiles and `~/.ssh/rc` that the rest of this depends
   on. An https remote would bypass the agent entirely and prompt for a password GitHub rejects.

How it works:

1. On the mac `ssh` uses whatever `IdentityAgent` names, which per ssh_config(5) overrides
   `SSH_AUTH_SOCK`. `.zprofile` and `.profile` export that variable too, since it is all that
   ssh-add and anything else skipping `~/.ssh/config` has to go on, and it is what remote hosts use.
2. One key serves every machine, registered once with GitHub. Remote hosts borrow it over the
   forwarded agent rather than holding a key of their own.
3. sshd gives each session a fresh socket path, which a long-lived tmux session outlives, so
   `~/.ssh/rc` keeps `~/.ssh/agent.sock` on a live socket and the profiles export that name instead.
   Without it, `git push` from a pane older than the current session fails.
