vim.api.nvim_create_user_command("D", function(opts)
    if vim.wo.diff then
			vim.cmd("diffo!")
        return
    end
	-- Get all currently visible windows
	-- local windows = vim.api.nvim_list_wins()
    -- NOTE: @goon - probably could have just done windo difft and windo diffo!
	local buffers = require("nvim_utils").get_visible_buffers()
	-- Apply difft to each visible window
	for _, buf in ipairs(buffers) do
		-- Execute diffoff in the context of each window
		vim.api.nvim_buf_call(buf, function()
			vim.cmd("difft")
		end)
	end
end, {
	desc = "Toggle diff mode on all visible buffers.",
})

