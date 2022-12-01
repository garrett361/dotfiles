-- Swap slash/backslash
local opts = { noremap = true, silent = true, buffer = 0 }
vim.keymap.set("i", "\\", "/", opts)
vim.keymap.set("i", "/", "\\", opts)
