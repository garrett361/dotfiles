vim.g.diagnostics_active = true
vim.api.nvim_create_user_command("ToggleDiagnostics", function()
	if vim.g.diagnostics_active then
		vim.g.diagnostics_active = false
		vim.diagnostic.hide()
	else
		vim.g.diagnostics_active = true
		vim.diagnostic.show()
	end
end, {})
