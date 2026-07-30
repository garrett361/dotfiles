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
	config = config,
	keys = {
		{ "<leader>cd", vim.lsp.buf.definition },
		{ "<leader>ce", vim.lsp.buf.declaration },
		{ "<leader>ci", vim.lsp.buf.hover },
		{ "<leader>cI", "<cmd>checkhealth vim.lsp<cr>" },
		{ "<leader>co", vim.diagnostic.open_float },
		{ "<leader>cr", vim.lsp.buf.references },
		{ "<leader>cR", vim.lsp.buf.rename },
		{
			"<leader>cs",
			function()
				vim.cmd([[:split]])
				vim.lsp.buf.definition()
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
