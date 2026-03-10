-- Copy relative path to system clipboard
vim.api.nvim_create_user_command("CopyPath", 'let @+=expand("%:.")', {})
-- Copy full/absolute path to system clipboard
vim.api.nvim_create_user_command("CopyPathFull", 'let @+=expand("%:p")', {})
-- Copy relative path as Python module notation (e.g., foo/bar.py -> foo.bar)
vim.api.nvim_create_user_command("CopyPathPy", 'let @+=substitute(substitute(expand("%:.:r"), "/", ".", "g"), "^\\\\.", "", "")', {})
-- Copy full/absolute path with line number or visual range (e.g., /abs/path:42 or /abs/path:10-20)
vim.api.nvim_create_user_command("CopyPathFullLoc", function(opts)
    local path = vim.fn.expand("%:p")
    local result = opts.line1 == opts.line2
        and path .. ":" .. opts.line1
        or path .. ":" .. opts.line1 .. "-" .. opts.line2
    vim.fn.setreg("+", result)
end, { range = true })
vim.keymap.set({ "n", "v" }, "<leader>zy", ":CopyPathFullLoc<CR>", { desc = "Copy path:line to clipboard" })
