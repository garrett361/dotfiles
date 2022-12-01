local function config()
	local prequire = require("nvim_utils").prequire
	prequire("user.lsp")
end
return {
	"neovim/nvim-lspconfig",
	lazy = false,
	priority = 1000, -- load first
	dependencies = {
		"williamboman/mason.nvim",
		"williamboman/mason-lspconfig.nvim",
		"hrsh7th/cmp-nvim-lsp-signature-help",
	},
	config = config,
	keys = {
		{
			"<leader>cd",
			function()
				vim.lsp.buf.definition()
			end,
		},
		{
			"<leader>ce",
			function()
				vim.lsp.buf.declaration()
			end,
		},
		{
			"<leader>cs",
			function()
				vim.cmd([[:split]])
				vim.lsp.buf.definition()
			end,
		},
		{
			"<leader>ci",
			function()
				vim.lsp.buf.hover()
			end,
		},
		{
			"<leader>cI",
			"<cmd>LspInfo<cr>",
		},
		{
			"<leader>cj",
			function()
				vim.diagnostic.goto_next({ buffer = 0 })
			end,
		},
		{
			"<leader>ck",
			function()
				vim.diagnostic.goto_prev({ buffer = 0 })
			end,
		},
		{
			"<leader>co",
			function()
				vim.diagnostic.open_float()
			end,
		},
		{
			"<leader>cr",
			function()
				vim.lsp.buf.references()
			end,
		},
		{
			"<leader>cR",
			function()
				vim.lsp.buf.rename()
			end,
		},
		{
			"<leader>cv",
			function()
				vim.cmd([[:vsplit]])
				vim.lsp.buf.definition()
			end,
		},
	},
}
