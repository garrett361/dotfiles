local function config()
	local ts = require("nvim_utils").prequire("nvim-treesitter")

	ts.install({
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
		"just",
		"latex",
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
	})
end

return {
	event = "VeryLazy",
	"nvim-treesitter/nvim-treesitter",
    branch="main",
	config = config,
}
