local M = {}
M.config = function()
	local prequire = require("nvim_utils").prequire
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

	-- Open on session start but never auto-close, matching the previous behavior. auto_toggle
	-- would also close when sessions end. The guard matters with one session per rank: open()
	-- begins with an unconditional close(), so an unguarded listener would tear the window
	-- down and rebuild it once per rank, stealing the cursor each time the repl is showing.
	local function open_if_closed()
		local state = prequire("dap-view.state")
		if not prequire("dap-view.util").is_win_valid(state.winnr) then
			dap_view.open()
		end
	end
	dap.listeners.before.attach.dap_view_config = open_if_closed
	dap.listeners.before.launch.dap_view_config = open_if_closed
end
return M
