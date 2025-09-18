local prequire = require("nvim_utils").prequire
local function config()
	local ts_context = require("nvim_utils").prequire("treesitter-context")
	vim.cmd("hi TreesitterContextLineNumberBottom gui=underline guisp=Grey")
	vim.cmd("hi TreesitterContextBottom gui=underline guisp=Grey")

	ts_context.setup({
		max_lines = 0,
		multiline_threshold = 3,
		trim_scope = "outer",
		multiwindow = "true",
	})
end
return {
	"nvim-treesitter/nvim-treesitter-context",
	event = "VeryLazy",
	config = config,
	keys = {
		{
			"<leader>cx",
			function()
				prequire("treesitter-context").go_to_context()
			end,
		},
	},
}
