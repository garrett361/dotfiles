local function config()
	local configs = require("nvim_utils").prequire("nvim-treesitter.configs")

	configs.setup({
		incremental_selection = {
			enable = false,
			keymaps = {
				init_selection = "<CR>",
				node_incremental = "<CR>",
				scope_incremental = "<Tab>",
				node_decremental = "<BS>",
			},
		},
		ensure_installed = {
			"bash",
			"bibtex",
			"c",
			"cmake",
			"cpp",
			"css",
			"cuda",
			"dockerfile",
			"html",
			"java",
			"javascript",
			"json",
			"lua",
			"luadoc",
			"make",
			"markdown",
			"markdown_inline",
			"python",
			"rst",
			"rust",
			"tsx",
			"typescript",
			"vim",
			"vimdoc",
			"yaml",
		}, -- one of "all" or a list of languages
		highlight = {
			enable = true, -- false will disable the whole extension
			disable = { "css" }, -- list of language that will be disabled
			additional_vim_regex_highlighting = { "markdown" },
		},
		indent = { enable = true, disable = {} },
	})
end

return {

	"nvim-treesitter/nvim-treesitter",
	config = config,
}
