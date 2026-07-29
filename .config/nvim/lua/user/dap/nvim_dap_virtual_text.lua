local M = {}
M.config = function()
	local nvim_dap_virtual_text = require("nvim_utils").prequire("nvim-dap-virtual-text")

	nvim_dap_virtual_text.setup({
		-- Default is "inline" on nvim 0.10+.
		virt_text_pos = "eol",
		-- Matches the plugin's own eol branch except that it leaves newlines and
		-- whitespace runs intact rather than collapsing them.
		display_callback = function(variable, _buf, _stackframe, _node)
			return variable.name .. " = " .. variable.value
		end,
	})
end
return M
