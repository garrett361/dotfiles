vim.api.nvim_create_user_command("MdTableFmt", function(opts)
    vim.cmd(opts.line1 .. "," .. opts.line2 .. "!sed 's/|/~|/g' | column -t -s '~'")
end, { range = true, desc = "Format markdown table in visual selection" })

vim.api.nvim_create_autocmd("FileType", {
    pattern = "markdown",
    callback = function()
        vim.keymap.set("v", "<leader>cf", ":MdTableFmt<CR>", { buffer = true, desc = "Format markdown table" })
    end,
})
