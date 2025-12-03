M = {}
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

---Run to cursor in all sessions
---@param sessions dap.Session[] | nil
---@param opts table|nil
local function run_to_cursor_all(sessions)
	sessions = sessions or get_sessions_with_frame()
	local api = vim.api
	local breakpoints = prequire("dap.breakpoints")
	local dap = prequire("dap")

	-- Save current breakpoints, then clear
	local bps_before = breakpoints.get()
	breakpoints.clear()
	local cur_bufnr = api.nvim_get_current_buf()
	local lnum = api.nvim_win_get_cursor(0)[1]
	breakpoints.set({}, cur_bufnr, lnum)

	local temp_bps = breakpoints.get(cur_bufnr)
	for bufnr, _ in pairs(bps_before) do
		if bufnr ~= cur_bufnr then
			temp_bps[bufnr] = {}
		end
	end

	if bps_before[cur_bufnr] == nil then
		bps_before[cur_bufnr] = {}
	end

	-- Track which sessions have stopped at cursor
	local sessions_stopped_at_cursor = {}
	local total_sessions = vim.tbl_count(sessions)

	local function restore_breakpoints_when_all_stopped()
		if vim.tbl_count(sessions_stopped_at_cursor) < total_sessions then
			return
		end

		-- Clean up listeners
		dap.listeners.before.event_stopped["dap.run_to_cursor"] = nil
		dap.listeners.before.event_terminated["dap.run_to_cursor"] = nil

		-- Restore original breakpoints
		breakpoints.clear()
		for buf, buf_bps in pairs(bps_before) do
			for _, bp in pairs(buf_bps) do
				local bp_opts = {
					condition = bp.condition,
					log_message = bp.logMessage,
					hit_condition = bp.hitCondition,
				}
				breakpoints.set(bp_opts, buf, bp.line)
			end
		end

		-- Set breakpoints for all sessions
		broadcast(sessions, function(session)
			session:set_breakpoints(bps_before, nil)
		end, false)
	end

	dap.listeners.before.event_stopped["dap.run_to_cursor"] = function(session)
		-- Only track sessions that are part of this operation
		if sessions[session.id] then
			sessions_stopped_at_cursor[session.id] = true
			restore_breakpoints_when_all_stopped()
		end
	end

	dap.listeners.before.event_terminated["dap.run_to_cursor"] = function(session)
		if sessions[session.id] then
			sessions_stopped_at_cursor[session.id] = true
			restore_breakpoints_when_all_stopped()
		end
	end

	local function set_temp_breakpoint(session)
		session:set_breakpoints(temp_bps, function()
			session:_step("continue")
		end)
	end

	broadcast(sessions, set_temp_breakpoint, false)
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

---Run selected sessions to a specific point
---@param sessions dap.Session[]
---@param target_bufnr integer
---@param target_lnum integer
local function run_sessions_to_point(sessions, target_bufnr, target_lnum)
	if vim.tbl_isempty(sessions) then
		vim.notify("No sessions selected", vim.log.levels.WARN)
		return
	end

	local breakpoints = prequire("dap.breakpoints")
	local dap = prequire("dap")

	-- Save current breakpoints, then clear
	local bps_before = breakpoints.get()
	breakpoints.clear()

	-- Set temporary breakpoint at target location
	breakpoints.set({}, target_bufnr, target_lnum)
	local temp_bps = breakpoints.get(target_bufnr)

	-- Ensure all other buffers have empty breakpoint tables
	for bufnr, _ in pairs(bps_before) do
		if bufnr ~= target_bufnr then
			temp_bps[bufnr] = {}
		end
	end

	if bps_before[target_bufnr] == nil then
		bps_before[target_bufnr] = {}
	end

	local sessions_stopped = {}
	local total_sessions = vim.tbl_count(sessions)

	local function restore_breakpoints()
		-- Only restore once all selected sessions have stopped
		if vim.tbl_count(sessions_stopped) < total_sessions then
			return
		end

		dap.listeners.before.event_stopped["dap.run_to_point"] = nil
		dap.listeners.before.event_terminated["dap.run_to_point"] = nil

		breakpoints.clear()
		for buf, buf_bps in pairs(bps_before) do
			for _, bp in pairs(buf_bps) do
				local bp_opts = {
					condition = bp.condition,
					log_message = bp.logMessage,
					hit_condition = bp.hitCondition,
				}
				breakpoints.set(bp_opts, buf, bp.line)
			end
		end

		-- Restore breakpoints for all sessions (not just selected ones)
		local all_sessions = get_sessions()
		for _, session in pairs(all_sessions) do
			if validate_session(session) then
				session:set_breakpoints(bps_before, nil)
			end
		end

		vim.notify("Selected sessions reached target point", vim.log.levels.INFO)
	end

	-- Track when each selected session stops
	dap.listeners.before.event_stopped["dap.run_to_point"] = function(session)
		if sessions[session.id] then
			sessions_stopped[session.id] = true
			restore_breakpoints()
		end
	end

	dap.listeners.before.event_terminated["dap.run_to_point"] = function(session)
		if sessions[session.id] then
			sessions_stopped[session.id] = true
			restore_breakpoints()
		end
	end

	-- Set temp breakpoint and continue for selected sessions only
	local function set_temp_breakpoint_and_continue(session)
		session:set_breakpoints(temp_bps, function()
			session:_step("continue")
		end)
	end

	broadcast(sessions, set_temp_breakpoint_and_continue, false)

	vim.notify(
		string.format(
			"Running %d selected sessions to %s:%d",
			total_sessions,
			vim.api.nvim_buf_get_name(target_bufnr),
			target_lnum
		),
		vim.log.levels.INFO
	)
end

---Main function: select sessions and run to point
local function run_selected_to_point()
	pick_sessions_multi_fzf(function(selected_sessions)
		if vim.tbl_isempty(selected_sessions) then
			vim.notify("No sessions selected", vim.log.levels.WARN)
			return
		end

		get_target_location(function(bufnr, lnum)
			run_sessions_to_point(selected_sessions, bufnr, lnum)
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
