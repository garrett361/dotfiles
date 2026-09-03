return {
	"MeanderingProgrammer/render-markdown.nvim",
	ft = "markdown",
	opts = {
		-- Off by default; toggle per-buffer with <leader>M.
		enabled = false,
	},
	keys = {
		{
			"<leader>M",
			"<cmd>RenderMarkdown buf_toggle<cr>",
			ft = "markdown",
			desc = "Toggle render-markdown",
		},
	},
}
