local prequire = require("nvim_utils").prequire

local function lint_config()
	local lint = prequire("lint")
	lint.linters_by_ft = {
		python = { "mypy" },
		-- lua = { "luacheck" },
	}
end

local function conform_config()
	local conform = prequire("conform")
	-- Ensure that ruff obeys any excludes in pyproject.toml
	conform.formatters.ruff_format = {
		inherit = false,
		meta = {
			url = "https://beta.ruff.rs/docs/",
			description = "An extremely fast Python linter, written in Rust. Formatter subcommand.",
		},
		command = "ruff",
		args = {
			"format",
			"--force-exclude",
			"--stdin-filename",
			"$FILENAME",
			"-",
		},
		stdin = true,
		cwd = require("conform.util").root_file({
			"pyproject.toml",
			"ruff.toml",
		}),
	}
	conform.setup({
		formatters_by_ft = {
			c = { "clang_format" },
			cpp = { "clang_format" },
			cuda = { "clang_format" },
			html = { "prettier" },
			javascript = { "prettier" },
			json = { "prettier" },
			lua = { "stylua" },
			markdown = { "prettier", "injected" },
			python = function(bufnr)
				if require("conform").get_formatter_info("ruff_format", bufnr).available then
					return { "ruff_fix", "ruff_format", "ruff_organize_imports" }
				else
					return { "isort", "black" }
				end
			end,
			typst = { "typstyle" },
			yaml = { "prettier" },
		},
		log_level = vim.log.levels.DEBUG,
	})
end

local function config()
	conform_config()
	lint_config()
end

local function maybe_fmt_and_lint()
	if vim.api.nvim_buf_get_option(0, "ma") and os.getenv("FORMAT_ON_NVIM") == "1" then
		prequire("conform").format({ bufnr = 0 })
		prequire("lint").try_lint()
	end
end

return {
	"stevearc/conform.nvim",
	dependencies = {
		"mfussenegger/nvim-lint",
	},
	config = config,
	lazy = true,
	keys = {
		{
			"<leader>cf",
			function()
				prequire("conform").format({ bufnr = 0 })
			end,
			mode = { "n", "v" },
		},
		{
			"<leader>w",
			function()
				maybe_fmt_and_lint()
				vim.cmd("w")
			end,
		},
		{
			"<leader>W",
			function()
				maybe_fmt_and_lint()
				vim.cmd("wq")
			end,
		},
	},
}
