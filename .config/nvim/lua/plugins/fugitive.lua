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
		local git_dir = vim.fn.FugitiveGitDir()
		if git_dir == "" then
			return
		end
		local w = vim.uv.new_fs_event()
		if not w then
			return
		end
		local timer = vim.uv.new_timer()
		w:start(git_dir, { recursive = false }, function()
			timer:stop()
			timer:start(100, 0, function()
				vim.schedule(function()
					vim.cmd("silent! call fugitive#DidChange()")
				end)
			end)
		end)
	end,
}
