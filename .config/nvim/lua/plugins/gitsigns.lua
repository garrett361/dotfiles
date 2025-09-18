local prequire = require("nvim_utils").prequire

local function config()
	local gitsigns = prequire("gitsigns")
	gitsigns.setup({
		signs = {
			add = { text = "+" },
			change = { text = "┃" },
			delete = { text = "_" },
			topdelete = { text = "‾" },
			changedelete = { text = "~" },
			untracked = { text = "┆" },
		},
		signs_staged = {
			add = { text = "+" },
			change = { text = "┃" },
			delete = { text = "_" },
			topdelete = { text = "‾" },
			changedelete = { text = "~" },
			untracked = { text = "┆" },
		},
	})
end
return {

	"lewis6991/gitsigns.nvim",
	config = config,
	event = "VeryLazy",
	keys = {
		{
			"<leader>aa",
			function()
				prequire("gitsigns").stage_hunk({ vim.fn.line("."), vim.fn.line("v") })
			end,
			mode = { "n", "v" },
		},
		{
			"<leader>aA",
			function()
				prequire("gitsigns").stage_buffer()
			end,
		},
		{
			"<leader>ap",
			function()
				prequire("gitsigns").preview_hunk()
			end,
		},
		{
			"<leader>ar",
			function()
				local mode = vim.api.nvim_get_mode().mode
				local not_visual = not mode:match("^[vV\22]")
				if not_visual then
					prequire("gitsigns").reset_hunk()
				else
					local start, stop = unpack(prequire("nvim_utils").get_vis_pos())
					prequire("gitsigns").reset_hunk({ start[2], stop[2] })
				end
			end,
			mode = { "n", "v" },
		},
		{
			"<leader>aR",
			function()
				prequire("gitsigns").reset_buffer()
			end,
		},
		{
			"<leader>au",
			function()
				prequire("gitsigns").undo_stage_hunk()
			end,
		},
		{
			"[h",
			function()
				prequire("gitsigns").prev_hunk()
			end,
			mode = { "n" },
		},
		{
			"]h",
			function()
				prequire("gitsigns").next_hunk()
			end,
			mode = { "n" },
		},
	},
}
