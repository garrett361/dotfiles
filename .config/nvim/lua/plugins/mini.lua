local prequire = require("nvim_utils").prequire
local function config()
	prequire("mini.icons").setup()
	local mini_ai = prequire("mini.ai")
	mini_ai.setup({
		-- Table with textobject id as fields, textobject specification as values.
		-- Also use this to disable builtin textobjects. See |MiniAi.config|.
		custom_textobjects = {
			-- Add other delimiters to b for "brackets"
			b = { { "%b()", "%b[]", "%b{}", "%b$$", '%b""', "%b''", "%b<>", "%b``" }, "^.().*().$" },
		},
		-- Module mappings. Use `''` (empty string) to disable one.
		mappings = {
			-- Main textobject prefixes
			around = "a",
			inside = "i",
			-- Next/last variants
			around_next = "an",
			inside_next = "in",
			around_last = "al",
			inside_last = "il",
			-- Move cursor to corresponding edge of `a` textobject
			goto_left = "g[",
			goto_right = "g]",
		},
		-- Number of lines within which textobject is searched
		n_lines = 50,
		-- How to search for object (first inside current line, then inside
		-- neighborhood). One of 'cover', 'cover_or_next', 'cover_or_prev',
		-- 'cover_or_nearest', 'next', 'previous', 'nearest'.
		search_method = "cover_or_next",
		-- Whether to disable showing non-error feedback
		silent = false,
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

	local mini_comment = prequire("mini.comment")
	mini_comment.setup({
		-- Options which control module behavior
		options = {
			-- Function to compute custom 'commentstring' (optional)
			custom_commentstring = nil,
			-- Whether to ignore blank lines
			ignore_blank_line = false,
			-- Whether to recognize as comment only lines without indent
			start_of_line = false,
			-- Whether to ensure single space pad for comment parts
			pad_comment_parts = true,
		},
		-- Module mappings. Use `''` (empty string) to disable one.
		mappings = {
			-- Toggle comment (like `gcip` - comment inner paragraph) for both
			-- Normal and Visual modes
			comment = "gc",
			-- Toggle comment on current line
			comment_line = "gcc",
			-- Define 'comment' textobject (like `dgc` - delete whole comment block)
			textobject = "gc",
		},
		-- Hook functions to be executed at certain stage of commenting
		hooks = {
			-- Before successful commenting. Does nothing by default.
			pre = function() end,
			-- After successful commenting. Does nothing by default.
			post = function() end,
		},
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
	mini_indentscope.setup( -- No need to copy this inside `setup()`. Will be used automatically.
		{
			-- Draw options
			draw = {
				-- Delay (in ms) between event and start of drawing scope indicator
				delay = 100,
				-- Animation rule for scope's first drawing. A function which, given
				-- next and total step numbers, returns wait time (in ms). See
				-- |MiniIndentscope.gen_animation| for builtin options. To disable
				-- animation, use `require('mini.indentscope').gen_animation.none()`.
				animation = mini_indentscope.gen_animation.none(),
				-- Symbol priority. Increase to display on top of more symbols.
				priority = 2,
			},
			-- Module mappings. Use `''` (empty string) to disable one.
			mappings = {
				-- Textobjects
				object_scope = "ii",
				object_scope_with_border = "ai",
				-- Motions (jump to respective border line; if not present - body line)
				goto_top = "[i",
				goto_bottom = "]i",
			},
			-- Options which control scope computation
			options = {
				-- Type of scope's border: which line(s) with smaller indent to
				-- categorize as border. Can be one of: 'both', 'top', 'bottom', 'none'.
				border = "both",
				-- Whether to use cursor column when computing reference indent.
				-- Useful to see incremental scopes with horizontal cursor movements.
				indent_at_cursor = false,
				-- Whether to first check input line to be a border of adjacent scope.
				-- Use it if you want to place cursor on function header to get scope of
				-- its body.
				try_as_border = false,
			},
			-- Which character to use for drawing scope indicator
			symbol = "╎",
		}
	)

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
	mini_tabline.setup({
		-- Whether to show file icons
		show_icons = true,
		-- Whether to set Vim's settings for tabline (make it always shown and
		-- allow hidden buffers)
		set_vim_settings = true,
		-- Where to show tabpage section in case of multiple vim tabpages.
		-- One of 'left', 'right', 'none'.
		tabpage_section = "left",
	})

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
		-- Add custom surroundings to be used on top of builtin ones. For more
		-- information with examples, see `:h MiniSurround.config`.
		custom_surroundings = nil,
		-- Duration (in ms) of highlight when calling `MiniSurround.highlight()`
		highlight_duration = 500,
		-- Module mappings. Use `''` (empty string) to disable one.
		mappings = {
			add = "<leader>sa", -- Add surrounding in Normal and Visual modes
			delete = "<leader>sd", -- Delete surrounding
			-- find = "<leader>sf", -- Find surrounding (to the right)
			-- find_left = "<leader>sF", -- Find surrounding (to the left)
			-- highlight = "<leader>sh", -- Highlight surrounding
			replace = "<leader>sc", -- Replace surrounding (changed sr->sc since it's more idiomatic)
			-- update_n_lines = "<leader>sn", -- Update `n_lines`
			-- suffix_last = "l", -- Suffix to search with "prev" method
			-- suffix_next = "n", -- Suffix to search with "next" method
		},
		-- Number of lines within which surrounding is searched
		n_lines = 20,
		-- Whether to respect selection type:
		-- - Place surroundings on separate lines in linewise mode.
		-- - Place surroundings on each line in blockwise mode.
		respect_selection_type = false,
		-- How to search for surrounding (first inside current line, then inside
		-- neighborhood). One of 'cover', 'cover_or_next', 'cover_or_prev',
		-- 'cover_or_nearest', 'next', 'prev', 'nearest'. For more details,
		-- see `:h MiniSurround.config`.
		search_method = "cover",
		-- Whether to disable showing non-error feedback
		silent = false,
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
		spotter = mini_jump2d.gen_pattern_spotter("[%a%d_]+"),
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
		spotter = mini_jump2d.gen_pattern_spotter("[?%]?%)?%}?%$?]"),
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

	local mini_bufremove = prequire("mini.bufremove")
	mini_bufremove.setup({
		-- Whether to set Vim's settings for buffers (allow hidden buffers)
		set_vim_settings = true,
		-- Whether to disable showing non-error feedback
		silent = false,
	})
end
return {
	"echasnovski/mini.nvim",
	version = false,
	config = config,
	event = "VeryLazy",
}
