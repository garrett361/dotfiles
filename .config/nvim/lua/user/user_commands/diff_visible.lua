vim.api.nvim_create_user_command("D", function(opts)
	-- Get all currently visible windows
	-- local windows = vim.api.nvim_list_wins()
	local buffers = require("nvim_utils").get_visible_buffers()
	-- Apply difft to each visible window
	for _, buf in ipairs(buffers) do
		-- Execute diffoff in the context of each window
		vim.api.nvim_buf_call(buf, function()
			vim.cmd("difft")
		end)
	end
end, {
	desc = "Diff all visible buffers",
})

vim.api.nvim_create_user_command("Do", function(opts)
	vim.cmd("diffo!")
end, {
	desc = "Turn off diff",
})
