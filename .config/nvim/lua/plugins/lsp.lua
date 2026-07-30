local function config()
	local prequire = require("nvim_utils").prequire
	prequire("user.lsp")
end
return {
	-- Eager on purpose: `config` loads user.lsp, which calls mason.setup(), which prepends Mason's
	-- bin dir to PATH. Everything else here depends on that having happened.
	"mason-org/mason.nvim",
	lazy = false,
	priority = 1000, -- load first
	dependencies = {
		"mason-org/mason-lspconfig.nvim",
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
			"<cmd>checkhealth vim.lsp<cr>",
		},
		{
			"<leader>cj",
			function()
				-- float defaults true in goto_next but false in jump, so it's explicit here.
				vim.diagnostic.jump({ count = 1, float = true })
			end,
		},
		{
			"<leader>ck",
			function()
				vim.diagnostic.jump({ count = -1, float = true })
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
