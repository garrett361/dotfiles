-- Turn formatting on and off
vim.api.nvim_create_user_command("FormatOff", function()
	vim.env.FORMAT_ON_NVIM = "0"
end, {})
vim.api.nvim_create_user_command("FormatOn", function()
	vim.env.FORMAT_ON_NVIM = "1"
end, {})
