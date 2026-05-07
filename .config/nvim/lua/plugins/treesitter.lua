-- https://www.reddit.com/r/neovim/comments/1pndf9e/my_new_nvimtreesitter_configuration_for_the_main/
local arch = vim.uv.os_uname().machine
local install_dir = vim.fn.stdpath("data") .. "/treesitter-" .. arch

local function config()
	require("nvim-treesitter.config").setup({ install_dir = install_dir })
	local ts = require("nvim-treesitter")

	-- State tracking for async parser loading
	local parsers_loaded = {}
	local parsers_pending = {}
	local parsers_failed = {}

	local ns = vim.api.nvim_create_namespace("treesitter.async")

	-- Helper to start highlighting, indentation, and folding
	local function start(buf, lang)
		local ok = pcall(vim.treesitter.start, buf, lang)
		if ok then
			vim.bo[buf].indentexpr = "v:lua.require'nvim-treesitter'.indentexpr()"
			-- vim.wo[0][0].foldexpr = "v:lua.vim.treesitter.foldexpr()"
			vim.wo[0][0].foldmethod = "expr"
		end
		return ok
	end

	-- Install core parsers after lazy.nvim finishes loading all plugins
	vim.api.nvim_create_autocmd("User", {
		pattern = "LazyDone",
		once = true,
		callback = function()
			ts.install({
				"bash",
				"bibtex",
				"c",
				"cmake",
				"comment",
				"cpp",
				"css",
				"cuda",
				"diff",
				"dockerfile",
				"fish",
				"git_config",
				"git_rebase",
				"gitcommit",
				"gitignore",
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
				"regex",
				"rust",
				"toml",
				"tsx",
				"typst",
				"vim",
				"vimdoc",
				"xml",
				"yaml",
			}, {
				max_jobs = 8,
			})
		end,
	})

	-- Decoration provider for async parser loading
	vim.api.nvim_set_decoration_provider(ns, {
		on_start = vim.schedule_wrap(function()
			if #parsers_pending == 0 then
				return false
			end
			for _, data in ipairs(parsers_pending) do
				if vim.api.nvim_buf_is_valid(data.buf) then
					if start(data.buf, data.lang) then
						parsers_loaded[data.lang] = true
					else
						parsers_failed[data.lang] = true
					end
				end
			end
			parsers_pending = {}
		end),
	})

	local group = vim.api.nvim_create_augroup("TreesitterSetup", { clear = true })

	local ignore_filetypes = {
		"checkhealth",
		"lazy",
		"mason",
		"snacks_dashboard",
		"snacks_notif",
		"snacks_win",
	}

	-- Auto-install parsers and enable highlighting on FileType
	vim.api.nvim_create_autocmd("FileType", {
		group = group,
		desc = "Enable treesitter highlighting and indentation (non-blocking)",
		callback = function(event)
			if vim.tbl_contains(ignore_filetypes, event.match) then
				return
			end

			local lang = vim.treesitter.language.get_lang(event.match) or event.match
			local buf = event.buf

			if parsers_failed[lang] then
				return
			end

			if parsers_loaded[lang] then
				-- Parser already loaded, start immediately (fast path)
				start(buf, lang)
			else
				-- Queue for async loading
				table.insert(parsers_pending, { buf = buf, lang = lang })
			end

			-- Auto-install missing parsers (async, no-op if already installed)
			ts.install({ lang })
		end,
	})
end

return {
	"nvim-treesitter/nvim-treesitter",
	lazy = false,
	branch = "main",
	build = ":TSUpdate",
	config = config,
}
