local M = {}
local prequire = require("nvim_utils").prequire

---Focus the repl in dap-view's window. No-op when that window is closed, so callers that
---may have just closed it (the <A-q> toggle) can call this unconditionally.
M.focus_repl = function()
	local state = prequire("dap-view.state")
	if prequire("dap-view.util").is_win_valid(state.winnr) then
		prequire("dap-view").jump_to_view("repl")
	end
end

M.config = function()
	local dap_view = prequire("dap-view")
	local dap = prequire("dap")
	dap_view.setup({
		winbar = {
			-- Every section except console. console stays out so program output gets its
			-- own always-visible window rather than a tab; that is also why <A-q> passes
			-- hide_terminal.
			--
			-- Two of these are unreliable with one session per rank, which matters here
			-- but is accepted rather than avoided. scopes/view.lua holds the session in a
			-- module-level upvalue across a yielding request, so with several ranks stopped
			-- at once one rank's variablesReference can be sent to another rank's session.
			-- The threads view reads a global threads_error and a stack_trace_errors table
			-- keyed only by thread id, which every debugpy rank shares, so one rank's error
			-- can surface under another. Watches are unaffected: their session is resolved
			-- per evaluation.
			sections = {
				"watches",
				"scopes",
				"exceptions",
				"breakpoints",
				"threads",
				"sessions",
				"repl",
			},
			default_section = "repl",
		},
	})

	-- dap-view sets winfixbuf on both of its windows and offers no way to turn it off, so
	-- nvim-dap's default "uselast" raises E1513 when stepping with the cursor in one of them:
	-- it writes the source buffer into the alternate window, which is then a fixed one. The
	-- string strategies all either do that or create a split, and nvim-dap's own set_cursor
	-- additionally focuses the target window unless the current filetype is dap-repl. A
	-- function gets full control: reuse a window already showing the file, else any window
	-- that permits a buffer switch, never create one, never change focus.
	-- No `normal! zv` to open folds around the stopped line, unlike nvim-dap's set_cursor:
	-- folds are disabled here (nofoldenable), so it would reveal nothing, and running it needs
	-- nvim_win_call to make the target window current, which is itself a visible window op.
	dap.defaults.fallback.switchbuf = function(bufnr, line, column)
		local function place(win)
			pcall(vim.api.nvim_win_set_cursor, win, { line, math.max(column - 1, 0) })
		end
		local wins = vim.api.nvim_tabpage_list_wins(0)
		for _, win in ipairs(wins) do
			if vim.api.nvim_win_get_buf(win) == bufnr then
				return place(win)
			end
		end
		for _, win in ipairs(wins) do
			if not vim.wo[win].winfixbuf then
				vim.api.nvim_win_set_buf(win, bufnr)
				return place(win)
			end
		end
	end

	-- Open on session start but never auto-close, matching the previous behavior. auto_toggle
	-- would also close when sessions end. The guard matters with one session per rank: open()
	-- begins with an unconditional close(), so an unguarded listener would tear the window
	-- down and rebuild it once per rank, stealing the cursor each time the repl is showing.
	local function open_if_closed()
		local state = prequire("dap-view.state")
		local util = prequire("dap-view.util")
		if util.is_win_valid(state.winnr) then
			return
		end
		dap_view.open()
		-- open() creates both windows with enter = false, so the cursor stays in whatever
		-- window it was in, which is not the repl. Scheduled so it runs after the rest of
		-- the launch/attach handler.
		vim.schedule(M.focus_repl)
	end
	dap.listeners.before.attach.dap_view_config = open_if_closed
	dap.listeners.before.launch.dap_view_config = open_if_closed
end
return M
