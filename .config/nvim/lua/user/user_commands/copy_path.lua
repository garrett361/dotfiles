-- Copy relative path to system clipboard
vim.api.nvim_create_user_command("CopyPath", 'let @+=expand("%:.")', {})
-- Copy full/absolute path to system clipboard
vim.api.nvim_create_user_command("CopyPathFull", 'let @+=expand("%:p")', {})
-- Copy relative path as Python module notation (e.g., foo/bar.py -> foo.bar)
vim.api.nvim_create_user_command("CopyPathPy", 'let @+=substitute(substitute(expand("%:.:r"), "/", ".", "g"), "^\\\\.", "", "")', {})
