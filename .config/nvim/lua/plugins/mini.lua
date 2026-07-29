local prequire = require("nvim_utils").prequire
local function config()
	prequire("mini.icons").setup()
	local mini_ai = prequire("mini.ai")
	mini_ai.setup({
		custom_textobjects = {
			-- Add other delimiters to b for "brackets"
			b = { { "%b()", "%b[]", "%b{}", '%b""', "%b''", "%b<>", "%b``" }, "^.().*().$" },
			-- Custom textobject for dollar signs
			["$"] = { "%$().-()%$" },
		},
	})

	local mini_bracketed = prequire("mini.bracketed")
	mini_bracketed.setup({
		-- First-level elements are tables describing behavior of a target:
		--
		-- - <suffix> - single character suffix. Used after `[` / `]` in mappings.
		--   For example, with `b` creates `[B`, `[b`, `]b`, `]B` mappings.
		--   Supply empty string `''` to not create mappings.
		--
		-- - <options> - table overriding target options.
		--
		-- See `:h MiniBracketed.config` for more info.

		comment = { suffix = "", options = {} },
	})

	-- TODO
	local mini_hipatterns = prequire("mini.hipatterns")
	vim.cmd("hi MiniHipatternsFixme guifg=#ff00c7")
	vim.cmd("hi MiniHipatternsHack guifg=#ff00c7")
	vim.cmd("hi MiniHipatternsTodo guifg=#ff00c7")
	vim.cmd("hi MiniHipatternsNote guifg=#ff00c7")
	mini_hipatterns.setup({
		highlighters = {
			-- Highlight standalone 'FIXME', 'HACK', 'TODO', 'NOTE'
			fixme = { pattern = "%f[%w]()FIXME()%f[%W]", group = "MiniHipatternsFixme" },
			hack = { pattern = "%f[%w]()HACK()%f[%W]", group = "MiniHipatternsHack" },
			todo = { pattern = "%f[%w]()TODO()%f[%W]", group = "MiniHipatternsTodo" },
			gg_todo = { pattern = "%f[%w]()GG_TODO()%f[%W]", group = "MiniHipatternsTodo" },
			note = { pattern = "%f[%w]()NOTE()%f[%W]", group = "MiniHipatternsNote" },
			gg_note = { pattern = "%f[%w]()GG_NOTE()%f[%W]", group = "MiniHipatternsNote" },
			-- Highlight hex color strings (`#rrggbb`) using that color
			hex_color = mini_hipatterns.gen_highlighter.hex_color(),
		},
	})

	local mini_indentscope = prequire("mini.indentscope")
	mini_indentscope.setup({
		draw = { animation = mini_indentscope.gen_animation.none() },
		-- Default is true; keep scopes stable under horizontal cursor movement.
		options = { indent_at_cursor = false },
	})

	local mini_pairs = prequire("mini.pairs")
	mini_pairs.setup({
		-- In which modes mappings from this `config` should be created
		modes = { insert = true, command = false, terminal = false },
		-- Global mappings. Each right hand side should be a pair information, a
		-- table with at least these fields (see more in |MiniPairs.map|):
		-- - <action> - one of 'open', 'close', 'closeopen'.
		-- - <pair> - two character string for pair to be used.
		-- By default pair is not inserted after `\`, quotes are not recognized by
		-- `<CR>`, `'` does not insert pair after a letter.
		-- Only parts of tables can be tweaked (others will use these defaults).
		mappings = {
			-- Force pairs to always write the closing bracket, in (almost) all cases.
			[")"] = { action = "close", pair = "()", neigh_pattern = "%(." },
			["]"] = { action = "close", pair = "[]", neigh_pattern = "%[." },
			["}"] = { action = "close", pair = "{}", neigh_pattern = "%{." },
			-- https://www.reddit.com/r/neovim/comments/1iuc54n/how_to_fix_this_minipair_issue/?chainedPosts=t3_1jh1r48
			["["] = {
				action = "open",
				pair = "[]",
				neigh_pattern = ".[%s%z%)}%]]",
				register = { cr = false },
			},
			["{"] = {
				action = "open",
				pair = "{}",
				neigh_pattern = ".[%s%z%)}%]]",
				register = { cr = false },
			},
			["("] = {
				action = "open",
				pair = "()",
				register = { cr = false },
				neigh_pattern = ".[%s%(%{%[%]%}%)]",
			},
			-- Open if next to white space or a bracket on both sides.
			['"'] = {
				action = "open",
				pair = '""',
				neigh_pattern = "[%s%(%{%[%]%}%)][%s%(%{%[%]%}%)]",
				register = { cr = false },
			},
			["'"] = {
				action = "open",
				pair = "''",
				neigh_pattern = "[%s%(%{%[%]%}%)][%s%(%{%[%]%}%)]",
				register = { cr = false },
			},
			["`"] = {
				action = "open",
				pair = "``",
				neigh_pattern = "[%s%(%{%[%]%}%)][%s%(%{%[%]%}%)]",
				register = { cr = false },
			},
		},
	})

	local mini_tabline = prequire("mini.tabline")
	mini_tabline.setup()

	local mini_statusline = prequire("mini.statusline")

	-- Custom function for summarizing diagnostics
	vim.cmd("hi MiniDiagnosticError guifg=#f80032")
	vim.cmd("hi MiniDiagnosticWarn guifg=#ffeb00")
	vim.cmd("hi MiniDiagnosticInfo guifg=#00a8f3")
	vim.cmd("hi MiniDiagnosticHint guifg=#b9e3ce")
	local diagnostic_levels = {
		error = { id = vim.diagnostic.severity.ERROR, sign = "" },
		warn = { id = vim.diagnostic.severity.WARN, sign = "" },
		info = { id = vim.diagnostic.severity.INFO, sign = "" },
		hint = { id = vim.diagnostic.severity.HINT, sign = "" },
	}
	local function statusline_diagnostics(args)
		-- Assumption: there are no attached clients if table
		-- `vim.lsp.buf_get_clients()` is empty
		local hasnt_attached_client = next(vim.lsp.get_clients()) == nil
		local not_regular_buffer = vim.bo.buftype ~= ""
		local dont_show_lsp = mini_statusline.is_truncated(args.trunc_width)
			or not_regular_buffer
			or hasnt_attached_client
		if dont_show_lsp then
			return ""
		end

		-- Construct diagnostic info using predefined order
		local t = {}
		local get_diagnostic_count = function(id)
			return #vim.diagnostic.get(0, { severity = id })
		end
		local n = get_diagnostic_count(args.level.id)
		-- Add level info only if diagnostic is present
		if n > 0 then
			table.insert(t, string.format("%s %s", args.level.sign, n))
		end

		if vim.tbl_count(t) == 0 then
			return ""
		end
		return string.format("%s", table.concat(t))
	end

	mini_statusline.setup({
		-- Content of statusline as functions which return statusline string. See
		-- `:h statusline` and code of default contents (used instead of `nil`).
		content = {
			-- Content for active window
			active = function()
				local mode, mode_hl = mini_statusline.section_mode({ trunc_width = 120 })
				local git = mini_statusline.section_git({ trunc_width = 75 })
				local diagnostic_error =
					statusline_diagnostics({ trunc_width = 75, level = diagnostic_levels.error })
				local diagnostic_warn =
					statusline_diagnostics({ trunc_width = 75, level = diagnostic_levels.warn })
				local diagnostic_info =
					statusline_diagnostics({ trunc_width = 75, level = diagnostic_levels.info })
				local diagnostic_hint =
					statusline_diagnostics({ trunc_width = 75, level = diagnostic_levels.hint })
				local filename = mini_statusline.section_filename({ trunc_width = 140 })
				local fileinfo = mini_statusline.section_fileinfo({ trunc_width = 120 })
				local location = mini_statusline.section_location({ trunc_width = 75 })

				local no_format_str = ""
				if vim.env.FORMAT_NVIM ~= "1" then
					no_format_str = "FORMAT OFF"
				end

				local py_venv = ""
				local snake = " "
				if vim.env.PYENV_VERSION ~= nil then
					py_venv = snake .. vim.env.PYENV_VERSION
				elseif vim.env.CONDA_PREFIX ~= nil then
					py_venv = snake .. vim.env.CONDA_PREFIX
				elseif vim.env.VIRTUAL_ENV ~= nil then
					py_venv = snake .. vim.env.VIRTUAL_ENV
				end

				return mini_statusline.combine_groups({
					{ hl = mode_hl, strings = { mode } },
					{ hl = "MiniStatuslineDevinfo", strings = { git } },
					{ hl = "MiniStatuslineDevinfo", strings = { py_venv } },
					"%<", -- Mark general truncate point
					{ hl = "MiniStatuslineFilename", strings = { filename } },
					{ hl = "MiniStatuslineFilename", strings = { location } },
					"%=", -- End left alignment
					{ hl = "MiniDiagnosticError", strings = { diagnostic_error } },
					{ hl = "MiniDiagnosticWarn", strings = { diagnostic_warn } },
					{ hl = "MiniDiagnosticInfo", strings = { diagnostic_info } },
					{ hl = "MiniDiagnosticHint", strings = { no_format_str } },
					-- { hl = "MiniStatuslineFileinfo", strings = { fileinfo } },
					-- { hl = mode_hl, strings = { location } },
				})
			end,
			-- Content for inactive window(s)
			inactive = nil,
		},
		-- Whether to use icons by default
		use_icons = true,
		-- Whether to set Vim's settings for statusline (make it always shown with
		-- 'laststatus' set to 2). To use global statusline in Neovim>=0.7.0, set
		-- this to `false` and 'laststatus' to 3.
		set_vim_settings = true,
	})

	local mini_surround = prequire("mini.surround")
	mini_surround.setup({
		mappings = {
			add = "<leader>sa", -- Add surrounding in Normal and Visual modes
			delete = "<leader>sd", -- Delete surrounding
			replace = "<leader>sc", -- Replace surrounding (sr->sc reads better)
		},
	})

	local mini_trailspace = prequire("mini.trailspace")
	mini_trailspace.setup({
		-- Highlight only in normal buffers (ones with empty 'buftype'). This is
		-- useful to not show trailing whitespace where it usually doesn't matter.
		only_in_normal_buffers = true,
	})
	vim.api.nvim_create_autocmd({ "BufWritePost" }, {
		callback = function()
			if os.getenv("FORMAT_NVIM") == "1" and vim.api.nvim_get_option_value("ma", {}) then
				mini_trailspace.trim()
			end
		end,
	})

	local mini_jump2d = prequire("mini.jump2d")
	vim.cmd("hi MiniJump2dSpot guifg=#8cedb4")
	vim.cmd("hi MiniJump2dSpotAhead guifg=#8cedb4")

	local jump_labels = "jkl'fdsam,.vcxyntgb"
	-- Start-of-word jumping
	local jump_to_start = {
		spotter = mini_jump2d.gen_spotter.pattern("[%a%d_]+"),
		labels = jump_labels,
		view = {
			n_steps_ahead = 10,
		},
		allowed_lines = {
			blank = true,
		},
		allowed_windows = {
			current = true,
			not_current = false,
		},
	}

	-- End-of-delimiter jumping
	local jump_to_delimiter = {
		spotter = mini_jump2d.gen_spotter.pattern("[?%]?%)?%}?%$?]"),
		labels = jump_labels,
		view = {
			n_steps_ahead = 10,
		},
		allowed_lines = {
			blank = false,
		},
		allowed_windows = {
			current = true,
			not_current = true,
		},
	}
	vim.keymap.set("n", "s", function()
		mini_jump2d.start(jump_to_start)
	end)
	vim.keymap.set("n", "S", function()
		mini_jump2d.start(jump_to_delimiter)
	end)
end
return {
	"echasnovski/mini.nvim",
	version = false,
	config = config,
	event = "VeryLazy",
}
