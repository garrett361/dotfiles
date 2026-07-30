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
		{ "<leader>cd", vim.lsp.buf.definition },
		{ "<leader>ce", vim.lsp.buf.declaration },
		{ "<leader>cs", "<cmd>split | lua vim.lsp.buf.definition()<cr>" },
		{ "<leader>ci", vim.lsp.buf.hover },
		{ "<leader>cI", "<cmd>checkhealth vim.lsp<cr>" },
		-- float defaults true in goto_next but false in jump, so it's explicit here.
		{ "<leader>cj", "<cmd>lua vim.diagnostic.jump({ count = 1, float = true })<cr>" },
		{ "<leader>ck", "<cmd>lua vim.diagnostic.jump({ count = -1, float = true })<cr>" },
		{ "<leader>co", vim.diagnostic.open_float },
		{ "<leader>cr", vim.lsp.buf.references },
		{ "<leader>cR", vim.lsp.buf.rename },
		{ "<leader>cv", "<cmd>vsplit | lua vim.lsp.buf.definition()<cr>" },
	},
}
