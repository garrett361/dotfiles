local M = {}
M.config = function()
	local prequire = require("nvim_utils").prequire
	local dap_view = prequire("dap-view")
	local dap = prequire("dap")
	dap_view.setup({
		winbar = {
			-- scopes and threads are left out on purpose. Both mishandle concurrent sessions:
			-- scopes/view.lua keeps the session in a module-level upvalue held across a
			-- yielding request, so one rank's variablesReference can be sent to another
			-- rank's session, and the threads view reads a global threads_error plus
			-- stack_trace_errors keyed only by thread id, which every debugpy rank shares.
			-- Omitting them means those paths never render. <A-F> covers stack navigation.
			sections = { "watches", "repl" },
			default_section = "watches",
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
