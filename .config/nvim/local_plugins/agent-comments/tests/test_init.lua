local hn = require("agent-comments")
local comments = require("agent-comments.comments")

T.test("init: comment_line adds a decorated comment via stubbed input", function()
	comments.clear()
	local ui = require("agent-comments.ui")
	local orig = ui.input_comment
	ui.input_comment = function(cb)
		cb("stub comment")
	end
	local b = vim.api.nvim_create_buf(false, true)
	vim.api.nvim_buf_set_lines(b, 0, -1, false, { "one", "two" })
	vim.api.nvim_set_current_buf(b)
	vim.api.nvim_win_set_cursor(0, { 2, 0 })
	hn.comment_line()
	ui.input_comment = orig
	local l = comments.list()
	T.eq(#l, 1)
	T.eq({ l[1].start_line, l[1].text }, { 2, "stub comment" })
end)

T.test("init: comment_selection uses the visual marks", function()
	comments.clear()
	local ui = require("agent-comments.ui")
	local orig = ui.input_comment
	ui.input_comment = function(cb)
		cb("stub sel")
	end
	local b = vim.api.nvim_create_buf(false, true)
	vim.api.nvim_buf_set_lines(b, 0, -1, false, { "a", "b", "c", "d" })
	vim.api.nvim_set_current_buf(b)
	vim.api.nvim_buf_set_mark(b, "<", 2, 0, {})
	vim.api.nvim_buf_set_mark(b, ">", 4, 0, {})
	hn.comment_selection()
	ui.input_comment = orig
	local list = comments.list()
	T.eq({ list[1].start_line, list[1].end_line }, { 2, 4 })
end)

T.test("init: comment_selection normalizes reversed marks", function()
	comments.clear()
	local ui = require("agent-comments.ui")
	local orig = ui.input_comment
	ui.input_comment = function(cb)
		cb("stub sel")
	end
	local b = vim.api.nvim_create_buf(false, true)
	vim.api.nvim_buf_set_lines(b, 0, -1, false, { "a", "b", "c", "d" })
	vim.api.nvim_set_current_buf(b)
	vim.api.nvim_buf_set_mark(b, "<", 4, 0, {})
	vim.api.nvim_buf_set_mark(b, ">", 2, 0, {})
	hn.comment_selection()
	ui.input_comment = orig
	local list = comments.list()
	T.eq({ list[1].start_line, list[1].end_line }, { 2, 4 })
end)

T.test("init: edit_comment updates text and refreshes its callout", function()
	comments.clear()
	local ui = require("agent-comments.ui")
	local b = vim.api.nvim_create_buf(false, true)
	vim.api.nvim_buf_set_lines(b, 0, -1, false, { "alpha" })
	local id = comments.add(b, 1, 1, "old text")
	ui.decorate(id)
	local c = comments.get(id)

	local original_input = vim.ui.input
	vim.ui.input = function(_, cb)
		cb("new text")
	end
	hn.edit_comment(c)
	vim.ui.input = original_input

	T.eq(comments.get(id).text, "new text")
	local marks = vim.api.nvim_buf_get_extmarks(b, ui.ns, 0, -1, { details = true })
	local callout_text
	for _, mark in ipairs(marks) do
		if mark[4].virt_lines then
			callout_text = mark[4].virt_lines[1][2][1]
		end
	end
	T.ok(callout_text and callout_text:find("new text", 1, true), "callout shows edited text")
end)

T.test("init: send_all formats, dispatches, clears", function()
	comments.clear()
	local b = vim.api.nvim_create_buf(false, true)
	vim.api.nvim_buf_set_lines(b, 0, -1, false, { "alpha" })
	vim.api.nvim_buf_set_name(b, "/tmp/hn-send.lua")
	comments.add(b, 1, 1, "check this")

	local ui = require("agent-comments.ui")
	local dispatch = require("agent-comments.dispatch")
	local agents = require("agent-comments.agents")
	local sent = {}
	local o1, o2, o3 = ui.pick_agent, dispatch.send, agents.list
	ui.pick_agent = function(_, cb)
		cb({ pane_id = "wZ:p9", title = "π", status = "idle" })
	end
	dispatch.send = function(pane, text, opts)
		sent = { pane, text, opts }
		return true
	end
	agents.list = function()
		return { { pane_id = "wZ:p9", title = "π", status = "idle" } }
	end

	hn.send_all({ submit = false })
	ui.pick_agent, dispatch.send, agents.list = o1, o2, o3

	T.eq(sent[1], "wZ:p9")
	T.ok(sent[2]:find("1. " .. vim.api.nvim_buf_get_name(b) .. ":1-1", 1, true))
	T.ok(sent[2]:find("   1 | alpha", 1, true))
	T.eq(sent[3].submit, false)
	T.eq(comments.list(), {}, "clear_after_send default clears comments")
end)

T.test("init: a send that clears the comments closes an open comment list", function()
	comments.clear()
	local ui = require("agent-comments.ui")
	local b = vim.api.nvim_create_buf(false, true)
	vim.api.nvim_buf_set_lines(b, 0, -1, false, { "alpha", "beta" })
	vim.api.nvim_buf_set_name(b, "/tmp/hn-send-list-open.lua")
	comments.add(b, 1, 1, "check this")
	comments.add(b, 2, 2, "and this")

	ui.comment_list({ edit = function() end, delete = function() end })
	local list_win = vim.api.nvim_get_current_win()
	T.ok(vim.api.nvim_win_is_valid(list_win), "the list must be open before the send")

	local dispatch = require("agent-comments.dispatch")
	local agents = require("agent-comments.agents")
	local o1, o2, o3 = ui.pick_agent, dispatch.send, agents.list
	ui.pick_agent = function(_, cb)
		cb({ pane_id = "wZ:p9", title = "pi", status = "idle" })
	end
	dispatch.send = function()
		return true
	end
	agents.list = function()
		return { { pane_id = "wZ:p9", title = "pi", status = "idle" } }
	end

	hn.send_all({ submit = false })
	ui.pick_agent, dispatch.send, agents.list = o1, o2, o3

	T.eq(comments.list(), {}, "the send clears the comment store")
	T.ok(not vim.api.nvim_win_is_valid(list_win), "the list must not outlive the comments it shows")
end)

T.test("init: with clear_after_send off a send leaves the list open and populated", function()
	comments.clear()
	local ui = require("agent-comments.ui")
	local b = vim.api.nvim_create_buf(false, true)
	vim.api.nvim_buf_set_lines(b, 0, -1, false, { "alpha" })
	vim.api.nvim_buf_set_name(b, "/tmp/hn-send-list-kept.lua")
	comments.add(b, 1, 1, "keep me")

	ui.comment_list({ edit = function() end, delete = function() end })
	local list_win = vim.api.nvim_get_current_win()
	local list_buf = vim.api.nvim_get_current_buf()

	local dispatch = require("agent-comments.dispatch")
	local agents = require("agent-comments.agents")
	local o1, o2, o3 = ui.pick_agent, dispatch.send, agents.list
	local previous_clear = hn.config.clear_after_send
	hn.config.clear_after_send = false
	ui.pick_agent = function(_, cb)
		cb({ pane_id = "wZ:p9", title = "pi", status = "idle" })
	end
	dispatch.send = function()
		return true
	end
	agents.list = function()
		return { { pane_id = "wZ:p9", title = "pi", status = "idle" } }
	end

	hn.send_all({ submit = false })
	ui.pick_agent, dispatch.send, agents.list = o1, o2, o3
	hn.config.clear_after_send = previous_clear

	T.eq(#comments.list(), 1, "clear_after_send off keeps the comments")
	T.ok(vim.api.nvim_win_is_valid(list_win), "the list stays open when nothing was cleared")
	T.eq(
		vim.api.nvim_buf_get_lines(list_buf, 0, -1, false),
		{ ui.comment_row(comments.list()[1]) },
		"the list still shows the surviving comment"
	)
	vim.api.nvim_win_close(list_win, true)
end)

T.test("init: send_all warns once when the resolved agent is working", function()
	comments.clear()
	local b = vim.api.nvim_create_buf(false, true)
	vim.api.nvim_buf_set_lines(b, 0, -1, false, { "alpha" })
	vim.api.nvim_buf_set_name(b, "/tmp/hn-send-working.lua")
	comments.add(b, 1, 1, "check this")

	local ui = require("agent-comments.ui")
	local dispatch = require("agent-comments.dispatch")
	local agents = require("agent-comments.agents")
	local warns = {}
	local o1, o2, o3, on = ui.pick_agent, dispatch.send, agents.list, vim.notify
	ui.pick_agent = function()
		error("picker must not open for a lone agent")
	end
	dispatch.send = function()
		return true
	end
	agents.list = function()
		return {
			{
				pane_id = "wZ:p9",
				tab_id = "wZ:t1",
				kind = "pi",
				title = "pi",
				status = "working",
				cwd = "/x/y/z",
			},
		}
	end
	vim.notify = function(msg, level)
		if level == vim.log.levels.WARN then
			table.insert(warns, msg)
		end
	end

	hn.send_all({ submit = true })
	ui.pick_agent, dispatch.send, agents.list, vim.notify = o1, o2, o3, on

	T.eq(#warns, 1, "working warning must fire exactly once")
	T.ok(warns[1]:find("is working", 1, true), "warning names the working state")
end)

T.test("init: send_all shows the picker when agents are ambiguous", function()
	comments.clear()
	local b = vim.api.nvim_create_buf(false, true)
	vim.api.nvim_buf_set_lines(b, 0, -1, false, { "alpha" })
	vim.api.nvim_buf_set_name(b, "/tmp/hn-send-multi.lua")
	comments.add(b, 1, 1, "check this")

	local ui = require("agent-comments.ui")
	local dispatch = require("agent-comments.dispatch")
	local agents = require("agent-comments.agents")
	local previous = vim.env.HERDR_TAB_ID
	vim.env.HERDR_TAB_ID = nil
	local picked, sent = false, {}
	local o1, o2, o3, o4 = ui.pick_agent, dispatch.send, agents.list, agents.resolve
	ui.pick_agent = function(l, cb)
		picked = true
		cb(l[1])
	end
	dispatch.send = function(pane)
		sent = { pane }
		return true
	end
	agents.list = function()
		return {
			{ pane_id = "wA:p1", tab_id = "wA:t1", title = "pi", status = "idle" },
			{ pane_id = "wB:p2", tab_id = "wB:t1", title = "claude", status = "idle" },
		}
	end
	-- Stubbed so an ambiguous list cannot reach a backend and query the real multiplexer.
	agents.resolve = function()
		return nil
	end

	hn.send_all({ submit = false })
	ui.pick_agent, dispatch.send, agents.list, agents.resolve = o1, o2, o3, o4
	vim.env.HERDR_TAB_ID = previous

	T.ok(picked, "picker must open when the target is ambiguous")
	T.eq(sent[1], "wA:p1")
end)

T.test("init: send_all skips the picker for a lone agent", function()
	comments.clear()
	local b = vim.api.nvim_create_buf(false, true)
	vim.api.nvim_buf_set_lines(b, 0, -1, false, { "alpha" })
	vim.api.nvim_buf_set_name(b, "/tmp/hn-send-solo.lua")
	comments.add(b, 1, 1, "check this")

	local ui = require("agent-comments.ui")
	local dispatch = require("agent-comments.dispatch")
	local agents = require("agent-comments.agents")
	local picked, sent = false, {}
	local o1, o2, o3 = ui.pick_agent, dispatch.send, agents.list
	ui.pick_agent = function()
		picked = true
	end
	dispatch.send = function(pane)
		sent = { pane }
		return true
	end
	agents.list = function()
		return { { pane_id = "wZ:p9", tab_id = "wZ:t1", title = "pi", status = "idle" } }
	end

	hn.send_all({ submit = false })
	ui.pick_agent, dispatch.send, agents.list = o1, o2, o3

	T.ok(not picked, "picker must not open for a single unambiguous agent")
	T.eq(sent[1], "wZ:p9")
end)

T.test("init: send_all retains comments when dispatch.send fails", function()
	comments.clear()
	local b = vim.api.nvim_create_buf(false, true)
	vim.api.nvim_buf_set_lines(b, 0, -1, false, { "alpha" })
	vim.api.nvim_buf_set_name(b, "/tmp/hn-send-fail.lua")
	comments.add(b, 1, 1, "check this")

	local ui = require("agent-comments.ui")
	local dispatch = require("agent-comments.dispatch")
	local agents = require("agent-comments.agents")
	local o1, o2, o3 = ui.pick_agent, dispatch.send, agents.list
	ui.pick_agent = function(_, cb)
		cb({ pane_id = "wZ:p9", title = "π", status = "idle" })
	end
	dispatch.send = function()
		return false, "boom"
	end
	agents.list = function()
		return { { pane_id = "wZ:p9", title = "π", status = "idle" } }
	end

	hn.send_all({ submit = false })
	ui.pick_agent, dispatch.send, agents.list = o1, o2, o3

	T.eq(#comments.list(), 1, "comments must be retained after a failed send")
end)

T.test("init: send_all reports a transport error and keeps the comment", function()
	comments.clear()
	local b = vim.api.nvim_create_buf(false, true)
	vim.api.nvim_buf_set_lines(b, 0, -1, false, { "alpha" })
	vim.api.nvim_buf_set_name(b, "/tmp/hn-send-no-session.lua")
	comments.add(b, 1, 1, "check this")

	local ui = require("agent-comments.ui")
	local dispatch = require("agent-comments.dispatch")
	local agents = require("agent-comments.agents")
	local errors, sends = {}, 0
	local o1, o2, o3, on = ui.pick_agent, dispatch.send, agents.list, vim.notify
	ui.pick_agent = function()
		error("picker must not open without a transport")
	end
	dispatch.send = function()
		sends = sends + 1
		return true
	end
	agents.list = function()
		return nil, "not in a herdr session (HERDR_WORKSPACE_ID is unset)"
	end
	vim.notify = function(msg, level)
		if level == vim.log.levels.ERROR then
			table.insert(errors, msg)
		end
	end

	hn.send_all({ submit = false })
	ui.pick_agent, dispatch.send, agents.list, vim.notify = o1, o2, o3, on

	T.eq(#errors, 1, "transport error must be reported once")
	T.ok(errors[1]:find("herdr session", 1, true), "error surfaces the transport reason")
	T.eq(sends, 0, "dispatch.send must not run without a transport")
	T.eq(#comments.list(), 1, "comments must survive a transport error")
end)

T.test("init: send_all marks a comment whose buffer has unwritten changes", function()
	comments.clear()
	local b = vim.api.nvim_create_buf(true, false)
	vim.api.nvim_buf_set_lines(b, 0, -1, false, { "alpha" })
	vim.api.nvim_buf_set_name(b, "/tmp/hn-send-unsaved.lua")
	comments.add(b, 1, 1, "check this")

	local ui = require("agent-comments.ui")
	local dispatch = require("agent-comments.dispatch")
	local agents = require("agent-comments.agents")
	local sent = {}
	local o1, o2, o3 = ui.pick_agent, dispatch.send, agents.list
	ui.pick_agent = function()
		error("picker must not open for a lone agent")
	end
	dispatch.send = function(_, text)
		sent = text
		return true
	end
	agents.list = function()
		return { { pane_id = "wZ:p9", title = "pi", status = "idle" } }
	end

	T.ok(vim.bo[b].modified, "a listed buffer is modified once lines are set")
	hn.send_all({ submit = false })
	ui.pick_agent, dispatch.send, agents.list = o1, o2, o3

	T.ok(sent:find("1. " .. vim.api.nvim_buf_get_name(b) .. ":1-1 [unsaved]", 1, true))
	T.ok(sent:find("Items marked [unsaved] quote my editor buffer", 1, true))
end)
