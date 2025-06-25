vim.api.nvim_create_user_command("Diff", function(opts)
	-- Get all currently visible windows
	local windows = vim.api.nvim_list_wins()
	-- Apply difft to each visible window
	for _, win in ipairs(windows) do
		-- Execute diffoff in the context of each window
		vim.api.nvim_win_call(win, function()
			vim.cmd("difft")
		end)
	end
end, {
	desc = "Diff all visible buffers",
})
