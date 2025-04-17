#!/bin/bash

# Rust
curl https://sh.rustup.rs -sSf | sh -s -- -y
source $HOME/.cargo/env
# cargo installs
cargo install tree-sitter-cli
cargo install starship
cargo install ripgrep
cargo install git-delta
cargo install bat
cargo install fd-find

