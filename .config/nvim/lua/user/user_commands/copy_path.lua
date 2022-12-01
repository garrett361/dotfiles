-- Copy pwd path to system clipboard
vim.api.nvim_create_user_command("CopyPath", 'let @+=expand("%")', {})
