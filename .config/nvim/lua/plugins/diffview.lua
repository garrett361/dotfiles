local prequire = require("nvim_utils").prequire
local function config()
	local diffview = prequire("diffview")
	-- Call the setup function to change the default behavior
	diffview.setup({
		ehnahced_diff_hl = true,
		keymaps = {
			file_panel = {
				{
					"n",
					"<down>",
					false,
				},
				{
					"n",
					"<up>",
					false,
				},
			},
			file_history_panel = {
				{
					"n",
					"<down>",
					false,
				},
				{
					"n",
					"<up>",
					false,
				},
			},
		},
	})
end

return {
	"dlyongemallo/diffview.nvim",
	lazy = true,
	config = config,
	cmd = "DiffviewOpen",
	keys = {
		{
			"<leader>ad",
			"<cmd>DiffviewOpen<cr>",
		},
		{
			"<leader>aD",
			":DiffviewOpen ",
		},
		{
			"<leader>aS",
			":DiffviewOpen --staged<cr>",
		},
		{
			"<leader>ah",
			"<cmd>DiffviewFileHistory %<cr>",
		},
		{
			"<leader>aq",
			"<cmd>DiffviewClose<cr>",
		},
	},
}
