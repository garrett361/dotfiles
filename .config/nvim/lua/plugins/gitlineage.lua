return {
	"lionyxml/gitlineage.nvim",
	lazy = true,
	dependencies = {
		"dlyongemallo/diffview.nvim", -- optional, for open_diff feature
	},
	config = function()
		require("gitlineage").setup({ keymap = "<leader>aL" })
	end,
	cmd = "GitLineage",
	keys = {
		{
			"<leader>aL",
			"GitLineage",
			mode = { "v", "n" },
		},
	},
}
