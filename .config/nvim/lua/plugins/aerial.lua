local prequire = require("nvim_utils").prequire
local function config()
	local aerial = prequire("aerial")

	-- Call the setup function to change the default behavior
	aerial.setup({
		-- Jump to symbol in source window when the cursor moves
		autojump = true,
		close_on_select = true,
		filter_kind = {
			"Class",
			"Constructor",
			"Enum",
			"Function",
			"Interface",
			"Module",
			"Method",
			"Namespace", -- For typst
			"Struct",
		},
	})
end
return {
	"stevearc/aerial.nvim",
	lazy = true,
	config = config,
	keys = {
		{
			"<leader>e",
			function()
				prequire("aerial").toggle({ direction = "right" })
			end,
		},
	},
}
