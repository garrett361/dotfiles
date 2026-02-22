return {
	"tpope/vim-fugitive",
	event = "VeryLazy",
	keys = {
		{
			"<leader>as",
			"<cmd>Gedit :<cr>",
		},
		{
			"<leader>aB",
			"<cmd>Git blame<cr>",
		},
	},
	config = function()
		vim.api.nvim_create_autocmd("FocusGained", {
			pattern = "*",
			callback = function()
				vim.cmd("silent! doautoall fugitive BufReadPost")
			end,
		})
	end,
}
