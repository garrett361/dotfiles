local prequire = require("nvim_utils").prequire

return {
	"retran/meow.yarn.nvim",
	lazy = true,
	dependencies = { "MunifTanjim/nui.nvim" },
	config = function()
		prequire("meow.yarn").setup({
			window = {
				width = 1.0,
				height = 1.0,
				border = "rounded",
				preview_height_ratio = 0.5,
			},
            expand_depth = 1
		})
	end,
	keys = {
		{
			"<leader>ch",
			function()
				prequire("meow.yarn").open_tree("call_hierarchy", "callers")
			end,
		},
		{
			"<leader>cH",
			function()
				prequire("meow.yarn").open_tree("type_hierarchy", "supertypes")
			end,
		},
	},
}
