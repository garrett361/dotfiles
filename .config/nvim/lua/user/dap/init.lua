local M = {}
local prequire = require("nvim_utils").prequire
M.config = function()
	prequire("user.dap.nvim_dap").config()
	prequire("user.dap.nvim_dap_lldb").config()
	prequire("user.dap.nvim_dap_python").config()
	prequire("user.dap.nvim_dap_ui").config()
	prequire("user.dap.nvim_dap_virtual_text").config()
end

---@class dap.Session

local default_timeouts = {
	rank_detection_timeout = 3000,
	session_wait_timeout = 5000,
	evaluation_test_timeout = 1000,
}

---Return the set of all dap sessions at same level as the present one.
---@return dap.Session[]
local function get_sessions()
	local dap = require("nvim_utils").prequire("dap")
	local curr_session = dap.session()
	if not curr_session.parent then
		return { [curr_session.id] = curr_session }
	end
	return curr_session.parent.children
end

---Return the set of all dap sessions at same level as the present one that have a current frame
---@return dap.Session[]
local function get_sessions_with_frame()
	local sessions = get_sessions()
	local sessions_with_frame = {}
	for _, s in pairs(sessions) do
		if s.current_frame then
			sessions_with_frame[s.id] = s
		end
	end
	return sessions_with_frame
end

---Wait for all sessions to be stopped, up to a timeout
---@param sessions dap.Session[]
---@param timeout_ms integer | nil
---@param interval_ms integer | nil
local function wait_for_sessions(sessions, timeout_ms, interval_ms)
	timeout_ms = timeout_ms or default_timeouts.session_wait_timeout
	interval_ms = interval_ms or 10

	local success = vim.wait(timeout_ms, function()
		for _, s in pairs(sessions) do
			if s.stopped_thread_id == nil then
				return false
			end
		end
		return true
	end, interval_ms, false)

	if not success then
		local session_states = {}
		for id, s in pairs(sessions) do
			table.insert(
				session_states,
				string.format("Session %s: %s", id, s.stopped_thread_id and "stopped" or "running")
			)
		end
		vim.notify(
			string.format(
				"Timeout after %dms waiting for sessions:\n%s",
				timeout_ms,
				table.concat(session_states, "\n")
			),
			vim.log.levels.WARN
		)
	end

	return success
end

local function validate_session(session)
	return session and session.id and not session.closed
end

---Apply fn to all sessions provided
---@param sessions dap.Session[] | nil
---@param fn fun(session: dap.Session)
---@param wait boolean | nil defaults to true
local function broadcast(sessions, fn, wait)
	if not sessions then
		error("No debug sessions provided.")
	end
	-- Ensure we restore the current session
	local dap = prequire("dap")
	local curr_session = dap.session()

	local errors = {}
	for id, s in pairs(sessions) do
		if validate_session(s) then
			local ok, err = pcall(fn, s)
			if not ok then
				table.insert(errors, string.format("Session %s: %s", id, err))
			end
		end
	end

	if #errors > 0 then
		vim.notify("Errors in DAP broadcast:\n" .. table.concat(errors, "\n"), vim.log.levels.ERROR)
		return false
	end

	local wait_success = true
	if wait or wait == nil then
		wait_success = wait_for_sessions(sessions)
		if not wait_success then
			vim.notify("Some sessions may not have completed the operation", vim.log.levels.WARN)
		end
	end

	if validate_session(curr_session) then
		dap.set_session(curr_session)
	end

	return wait_success
end

---Step over in all sessions
---@param sessions dap.Session[] | nil
---@param opts table|nil
---@return boolean success
local function step_over_all(sessions, opts)
	sessions = sessions or get_sessions_with_frame()
	local success = broadcast(sessions, function(s)
		s:_step("next", opts)
	end)

	if not success then
		vim.notify("Step over operation may have failed on some sessions", vim.log.levels.WARN)
	end
	return success
end

---Continue in all sessions
---@param sessions dap.Session[] | nil
---@return boolean success
local function continue_all(sessions)
	sessions = sessions or get_sessions_with_frame()
	local success = broadcast(sessions, function(s)
		s:_step("continue")
	end)

	if not success then
		vim.notify("Continue operation may have failed on some sessions", vim.log.levels.WARN)
	end
	return success
end

---Step into in all sessions
---@param sessions dap.Session[] | nil
---@param opts table|nil
local function step_into_all(sessions, opts)
	sessions = sessions or get_sessions_with_frame()
	broadcast(sessions, function(s)
		s:_step("stepIn", opts)
	end)
end

---Step out in all sessions
---@param sessions dap.Session[] | nil
---@param opts table|nil
local function step_out_all(sessions, opts)
	sessions = sessions or get_sessions_with_frame()
	broadcast(sessions, function(s)
		s:_step("stepOut", opts)
	end)
end

---Run to specified point in all sessions. Works by saving current breakpoints in a list, clearing
---them all, setting a temp breakpoint, running to the spot, and finally restoring old ckpts.
---@param sessions dap.Session[]
---@param target_bufnr integer
---@param target_lnum integer
local function run_to_point(sessions, target_bufnr, target_lnum)
	if vim.tbl_isempty(sessions) then
		vim.notify("No sessions to run", vim.log.levels.WARN)
		return
	end

	local breakpoints = prequire("dap.breakpoints")
	local dap = prequire("dap")

	-- Save current breakpoints, then clear
	local prev_breakpoints = breakpoints.get()
	breakpoints.clear()

	-- Set temporary breakpoint at target location
	breakpoints.set({}, target_bufnr, target_lnum)
	local temp_breakpoint = breakpoints.get()

	-- Track which sessions have stopped at cursor
	local sessions_stopped_at_cursor = {}
	local total_sessions = vim.tbl_count(sessions)

	-- Callback for restoring old breakpoints after we run to new breakpoint at cursor
	---@param session dap.Session[] | nil
	local function restore_prev_breakpoints(session)
		-- Only track sessions that are part of this operation
		if sessions[session.id] then
			sessions_stopped_at_cursor[session.id] = true
		end
		local all_procs_stopped_at_cursor = (
			vim.tbl_count(sessions_stopped_at_cursor) == total_sessions
		)
		if not all_procs_stopped_at_cursor then
			return
		end

		-- Clean up listeners
		dap.listeners.before.event_stopped["dap.run_to_cursor"] = nil
		dap.listeners.before.event_terminated["dap.run_to_cursor"] = nil

		-- Restore original breakpoints
		broadcast(sessions, function(session)
			session:set_breakpoints(prev_breakpoints, nil)
		end, false)
	end

	dap.listeners.before.event_stopped["dap.run_to_cursor"] = restore_prev_breakpoints
	dap.listeners.before.event_terminated["dap.run_to_cursor"] = restore_prev_breakpoints

	-- Set the temp breakpoint and run all procs to it
	local function set_temp_breakpoint(session)
		session:set_breakpoints(temp_breakpoint, function()
			session:_step("continue")
		end)
	end

	broadcast(sessions, set_temp_breakpoint, false)
end

---Run to cursor in all sessions
---@param sessions dap.Session[] | nil
---@param opts table|nil
local function run_to_cursor_all(sessions)
	sessions = sessions or get_sessions_with_frame()
	local api = vim.api

	local cur_bufnr = api.nvim_get_current_buf()
	local lnum = api.nvim_win_get_cursor(0)[1]

	run_to_point(sessions, cur_bufnr, lnum)
end

local cached_ranks = {}
local function get_rank_cached(session)
	-- Use cached rank if available and session is still valid
	if cached_ranks[session.id] then
		return cached_ranks[session.id]
	end

	if session.filetype ~= "python" then
		return "ERR"
	end

	local rank = nil
	local done = false

	-- Quick evaluation test to see if we're in a good state
	local can_evaluate = false
	session:evaluate("1 + 1", function(err, resp)
		can_evaluate = not err and resp and resp.result == "2"
		done = true
	end)

	local evaluation_success = vim.wait(default_timeouts.evaluation_test_timeout, function()
		return done
	end, 10, false)

	if not evaluation_success then
		vim.notify(
			string.format("Evaluation timeout for session %s", session.id),
			vim.log.levels.DEBUG
		)
		return cached_ranks[session.id] or "ERR"
	end

	if not can_evaluate then
		return cached_ranks[session.id] or "ERR"
	end

	-- Reset for actual rank detection
	done = false

	-- Evaluate is done in the repl env so state is persisted, allowing us to import.
	session:evaluate("import os", function(err, _)
		if err then
			rank = cached_ranks[session.id] or "ERR"
			done = true
			return
		end

		session:evaluate("os.getenv('RANK', 'UNK')", function(err, resp)
			if not err then
				rank = tostring(resp.result)
			else
				rank = cached_ranks[session.id] or "ERR"
			end
			done = true
		end)
	end)

	-- Wait for the callback to complete
	local callback_success = vim.wait(default_timeouts.rank_detection_timeout, function()
		return done
	end, 10, false)

	if not callback_success then
		vim.notify(
			string.format("Rank detection timeout for session %s", session.id),
			vim.log.levels.DEBUG
		)
		return cached_ranks[session.id] or "ERR"
	end

	if rank == "'UNK'" then
		done = false
		session:evaluate("import torch.distributed as dist", function(err, _)
			if err then
				rank = cached_ranks[session.id] or "ERR"
				done = true
				return
			end

			session:evaluate("dist.get_rank()", function(err, resp)
				if not err then
					rank = tostring(resp.result)
				else
					rank = cached_ranks[session.id] or "ERR"
				end
				done = true
			end)
		end)

		-- Wait for the callback to complete
		vim.wait(default_timeouts.rank_detection_timeout, function()
			return done
		end, 10, false)
	end

	-- Cache successful rank detection
	if rank and rank ~= "ERR" and rank ~= "'UNK'" then
		cached_ranks[session.id] = rank
	end

	return rank or cached_ranks[session.id] or "ERR"
end

local function pick_session_fzf(sessions)
	sessions = sessions or get_sessions_with_frame()
	local fzf = prequire("fzf-lua")
	local dap = prequire("dap")

	-- Clean up cached ranks for sessions that no longer exist
	for cached_id, _ in pairs(cached_ranks) do
		if not sessions[cached_id] then
			cached_ranks[cached_id] = nil
		end
	end

	local id_to_rank = {}
	for k, s in pairs(sessions) do
		local id = k
		id_to_rank[id] = get_rank_cached(s)
	end

	local current_str = " (CURRENT)"
	local fzf_table = {}

	for id, rank in pairs(id_to_rank) do
		local key
		-- Use rank if available, otherwise fall back to ID
		if rank ~= "ERR" and rank ~= "'UNK'" then
			key = "[rank = " .. rank .. "] (dap sess id = " .. tostring(id) .. ")"
		else
			key = tostring(id)
		end

		if id == dap.session().id then
			key = key .. current_str
		end
		fzf_table[key] = id
	end

	local fzf_keys = {}
	for k, _ in pairs(fzf_table) do
		table.insert(fzf_keys, k)
	end
	table.sort(fzf_keys)

	fzf.fzf_exec(fzf_keys, {
		prompt = "Choose DAP Session",
		actions = {
			["default"] = function(selected)
				dap.set_session(sessions[fzf_table[selected[1]]])
			end,
		},
	})
end

---Multi-select session picker that returns selected sessions
---@param callback fun(sessions: dap.Session[])
local function pick_sessions_multi_fzf(callback)
	local sessions = get_sessions_with_frame()
	local fzf = prequire("fzf-lua")

	-- Clean up stale cached ranks
	for cached_id, _ in pairs(cached_ranks) do
		if not sessions[cached_id] then
			cached_ranks[cached_id] = nil
		end
	end

	local id_to_rank = {}
	for k, s in pairs(sessions) do
		id_to_rank[k] = get_rank_cached(s)
	end

	local fzf_table = {}
	local fzf_keys = {}

	for id, rank in pairs(id_to_rank) do
		local key
		if rank ~= "ERR" and rank ~= "'UNK'" then
			key = "[rank = " .. rank .. "] (dap sess id = " .. tostring(id) .. ")"
		else
			key = tostring(id)
		end
		fzf_table[key] = id
		table.insert(fzf_keys, key)
	end
	table.sort(fzf_keys)

	fzf.fzf_exec(fzf_keys, {
		prompt = "Select DAP Sessions (TAB to multi-select)> ",
		fzf_opts = { ["--multi"] = true },
		actions = {
			["default"] = function(selected)
				local selected_sessions = {}
				for _, key in ipairs(selected) do
					local session_id = fzf_table[key]
					selected_sessions[session_id] = sessions[session_id]
				end
				callback(selected_sessions)
			end,
		},
	})
end

---Get target location for run-to-point
---@param callback fun(bufnr: integer, lnum: integer)
local function get_target_location(callback)
	local current_file = vim.api.nvim_buf_get_name(0)
	local file_input = vim.fn.input("Target file (default: current): ", current_file)
	if file_input == "" then
		file_input = current_file
	end

	-- Expand path and get buffer number
	local full_path = vim.fn.expand(file_input)
	local bufnr = vim.fn.bufnr(full_path, true) -- Create buffer if it doesn't exist

	if bufnr == -1 then
		vim.notify("Could not find/create buffer for: " .. full_path, vim.log.levels.ERROR)
		return
	end

	local line_input = vim.fn.input("Target line number: ")
	local lnum = tonumber(line_input)

	if not lnum or lnum <= 0 then
		vim.notify("Invalid line number: " .. tostring(line_input), vim.log.levels.ERROR)
		return
	end

	callback(bufnr, lnum)
end

local function run_selected_to_point()
	pick_sessions_multi_fzf(function(selected_sessions)
		if vim.tbl_isempty(selected_sessions) then
			vim.notify("No sessions selected", vim.log.levels.WARN)
			return
		end

		get_target_location(function(bufnr, lnum)
			run_to_point(selected_sessions, bufnr, lnum)
		end)
	end)
end

M.lazy_keymaps = {
	{
		"<A-a>",
		function()
			pick_session_fzf()
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-A>",
		function()
			prequire("fzf-lua").dap_breakpoints()
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-b>",
		function()
			prequire("dap").toggle_breakpoint()
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-B>",
		function()
			prequire("dap").clear_breakpoints()
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-c>",
		function()
			prequire("dap").set_breakpoint(vim.fn.input("Breakpoint condition: "))
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-C>",
		function()
			prequire("dap-python").test_class({ config = { justMyCode = true } })
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-d>",
		function()
			local dap = prequire("dap")
			if dap.session() == nil then
				dap.continue()
			else
				continue_all()
			end
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-e>",
		function()
			prequire("dapui").eval()
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-f>",
		function()
			-- :RustLsp is created buffer-locally in rustaceanvim's on_attach, so an
			-- unguarded call raises E492 before rust-analyzer has attached.
			if vim.bo.filetype == "rust" and vim.fn.exists(":RustLsp") == 2 then
				vim.cmd.RustLsp("debuggables")
				return
			end
			prequire("dap-python").test_method({
				config = { justMyCode = false, subProcess = true },
			})
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-F>",
		function()
			prequire("fzf-lua").dap_frames()
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-g>",
		function()
			step_over_all()
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-G>",
		function()
			prequire("dap").focus_frame()
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-q>",
		function()
			prequire("dapui").toggle({ layout = 1, reset = true })
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-Q>",
		function()
			-- Open the secondary dap window with stacks, watches, etc
			prequire("dapui").toggle({ layout = 2, reset = true })
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-r>",
		function()
			local dap = prequire("dap")
			if dap.session() == nil then
				dap.run_last()
			else
				dap.restart()
			end
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-s>",
		function()
			step_into_all()
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-S>",
		function()
			step_out_all()
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-x>",
		function()
			prequire("dap").terminate()
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-t>",
		function()
			run_to_cursor_all()
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-v>",
		function()
			prequire("dap").up()
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-V>",
		function()
			prequire("dap").down()
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-z>",
		function()
			prequire("fzf-lua").dap_commands()
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
	},
	{
		"<A-T>", -- Shift+Alt+t for selective run-to-point
		function()
			run_selected_to_point()
		end,
		mode = { "n" },
		noremap = true,
		silent = true,
		desc = "Run selected ranks to specific point",
	},
	{
		"<A-D>", -- Debug session states
		function()
			local sessions = get_sessions()
			for id, s in pairs(sessions) do
				print(
					string.format(
						"Session %s: stopped_thread=%s, frame=%s, closed=%s",
						id,
						tostring(s.stopped_thread_id),
						tostring(s.current_frame ~= nil),
						tostring(s.closed)
					)
				)
			end
		end,
		mode = { "n" },
		desc = "Debug session states",
	},
}

return M
