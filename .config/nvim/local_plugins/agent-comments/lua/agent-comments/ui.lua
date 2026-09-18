local M = {}
local comments = require("agent-comments.comments")
local agents = require("agent-comments.agents")

-- Separate from comments.ns so a query means one thing: comments.ns holds exactly
-- one range-tracking extmark per comment, this one holds only drawing.
M.ns = vim.api.nvim_create_namespace("agent-comments-decorations")

-- An annotated block is drawn as three cooperating layers:
--   * a solid amber rail in the SIGN COLUMN, one cell per line of the block
--   * a subtle full-width background tint over those same lines
--   * a callout above the first line naming the comment
--
-- The rail lives in the sign column rather than as inline virt_text on purpose:
-- inline text shifts the annotated code sideways, so a block visibly jumps out
-- of alignment with the rest of the file the moment you comment on it.
--
-- The colour is a dedicated amber, NOT a link to DiagnosticWarn. Borrowing the
-- diagnostic colour makes comments compete with real warnings for the same
-- visual meaning. Override any of these highlights to retheme.
local function set_highlights()
	vim.api.nvim_set_hl(0, "AgentCommentsSign", { default = true, fg = "#d7a65f", bold = true })
	vim.api.nvim_set_hl(0, "AgentCommentsText", { default = true, fg = "#d7a65f" })
	-- Tint stays deliberately quiet -- the rail carries the colour. Linked to
	-- CursorLine so it tracks whatever the active colourscheme uses for "this
	-- region is active", on light and dark themes alike.
	vim.api.nvim_set_hl(0, "AgentCommentsLine", { default = true, link = "CursorLine" })
end

set_highlights()

-- A :colorscheme clears every highlight, so these have to be laid down again after one.
vim.api.nvim_create_autocmd("ColorScheme", {
	group = vim.api.nvim_create_augroup("AgentCommentsHighlights", { clear = true }),
	callback = set_highlights,
})

local decorations = {} -- comment id -> { hl, callout, bufnr }

-- There is only ever one comment list, tracked here so code outside comment_list()
-- (a send, say) can refresh or close it.
local open_list = nil

function M.visual_range()
	local s = vim.api.nvim_buf_get_mark(0, "<")[1]
	local e = vim.api.nvim_buf_get_mark(0, ">")[1]
	if s > e then
		s, e = e, s
	end
	return s, e
end

function M.input_comment(on_done)
	vim.ui.input({ prompt = "Comment: " }, function(text)
		if text and text ~= "" then
			on_done(text)
		end
	end)
end

-- The callout rendered ABOVE the first annotated line. Above, not below: a note
-- sitting under its block reads as a label for whatever code follows it.
-- The corner opens downward (╭─) into the rail beneath it.
function M._callout(text)
	return { { { "╭─ ", "AgentCommentsSign" }, { "💬 " .. text, "AgentCommentsText" } } }
end

function M.decorate(id)
	local c = comments.get(id)
	if not c then
		return
	end
	local ns = M.ns
	-- 1. Rail + tint on every line of the block. ▌ (half block) fills the sign
	--    cell solidly, so the rail reads as one continuous stripe down the block
	--    instead of a dotted column of glyphs.
	local bars = {}
	for line = c.start_line, c.end_line do
		bars[#bars + 1] = vim.api.nvim_buf_set_extmark(c.bufnr, ns, line - 1, 0, {
			sign_text = "▌",
			sign_hl_group = "AgentCommentsSign",
			line_hl_group = "AgentCommentsLine",
			right_gravity = false,
		})
	end

	-- 2. Callout above the first line, opening into the rail below it.
	local callout = vim.api.nvim_buf_set_extmark(c.bufnr, ns, c.start_line - 1, 0, {
		virt_lines = M._callout(c.text),
		virt_lines_above = true,
	})
	decorations[id] = { bars = bars, callout = callout, bufnr = c.bufnr }
end

function M.undecorate(id)
	local marks = decorations[id]
	if marks and vim.api.nvim_buf_is_valid(marks.bufnr) then
		for _, bar in ipairs(marks.bars) do
			vim.api.nvim_buf_del_extmark(marks.bufnr, M.ns, bar)
		end
		vim.api.nvim_buf_del_extmark(marks.bufnr, M.ns, marks.callout)
	end
	decorations[id] = nil
end

function M.comment_row(c)
	return string.format(
		"%s:%d-%d  %s",
		vim.fn.fnamemodify(c.file, ":t"),
		c.start_line,
		c.end_line,
		c.text
	)
end

-- Interactive comment list: a rounded floating box (with a shortcut-hint footer)
-- listing one row per comment. Moving the cursor auto-previews (jumps the code
-- window to that comment); <CR> jumps, `e` edits, `dd` deletes, `q`/<Esc> cancels.
-- `handlers.edit(c, refresh)` and `handlers.delete(c)` do the actual work.
function M.comment_list(handlers)
	-- Ahead of the no-comments early return below, so a list left behind by any path that forgot
	-- to close it can never strand a float the user cannot reopen and dismiss.
	if open_list then
		open_list.dismiss()
	end
	local code_win = vim.api.nvim_get_current_win()
	-- Browsing the list previews by moving the code window. Save where it was so cancelling puts
	-- it back; only <CR> is allowed to leave the window somewhere new.
	local origin = {
		buf = vim.api.nvim_win_get_buf(code_win),
		view = vim.api.nvim_win_call(code_win, vim.fn.winsaveview),
	}
	local rows = comments.list()
	if #rows == 0 then
		vim.notify("agent-comments: no comments", vim.log.levels.INFO)
		return
	end

	local buf = vim.api.nvim_create_buf(false, true)
	vim.bo[buf].bufhidden = "wipe"
	vim.bo[buf].filetype = "agent-comments"

	local function win_config()
		local width = 46
		for _, c in ipairs(rows) do
			width = math.max(width, vim.fn.strdisplaywidth(M.comment_row(c)) + 2)
		end
		width = math.min(width, math.max(46, vim.o.columns - 6))
		local height = math.max(1, math.min(#rows, 12))
		return {
			relative = "editor",
			width = width,
			height = height,
			row = math.max(0, vim.o.lines - height - 4),
			col = math.max(0, math.floor((vim.o.columns - width) / 2)),
			style = "minimal",
			border = "rounded",
			title = { { " 💬 Comments ", "AgentCommentsText" } },
			title_pos = "center",
			footer = {
				{
					" ↑↓ preview  ·  ⏎ jump  ·  e edit  ·  dd delete  ·  q cancel ",
					"Comment",
				},
			},
			footer_pos = "center",
		}
	end

	local win = vim.api.nvim_open_win(buf, true, win_config())
	vim.wo[win].cursorline = true
	vim.wo[win].wrap = false

	local grp = vim.api.nvim_create_augroup("AgentCommentsList" .. buf, { clear = true })

	local function restore()
		if not vim.api.nvim_win_is_valid(code_win) or not vim.api.nvim_buf_is_valid(origin.buf) then
			return
		end
		if vim.api.nvim_win_get_buf(code_win) ~= origin.buf then
			-- Same E37 guard as preview(): a modified buffer with 'hidden' off refuses to swap out.
			if not pcall(vim.api.nvim_win_set_buf, code_win, origin.buf) then
				return
			end
		end
		vim.api.nvim_win_call(code_win, function()
			vim.fn.winrestview(origin.view)
		end)
	end

	-- Set by every deliberate takedown, so the WinLeave handler below stays out of the way. Every
	-- exit path funnels through dismiss(), <CR> included, and closing the float fires WinLeave.
	local closing = false

	local function dismiss()
		closing = true
		if vim.api.nvim_win_is_valid(win) then
			vim.api.nvim_win_close(win, true)
		end
		pcall(vim.api.nvim_del_augroup_by_id, grp)
		-- Guarded so a dismiss arriving late cannot drop a list opened since.
		if open_list and open_list.win == win then
			open_list = nil
		end
	end

	local function close()
		restore()
		dismiss()
	end

	local function render()
		rows = comments.list()
		if #rows == 0 then
			close()
			return false
		end
		local lines = {}
		for _, c in ipairs(rows) do
			lines[#lines + 1] = M.comment_row(c)
		end
		vim.bo[buf].modifiable = true
		vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
		vim.bo[buf].modifiable = false
		if vim.api.nvim_win_is_valid(win) then
			vim.api.nvim_win_set_config(win, win_config())
		end
		return true
	end

	local function current()
		if not vim.api.nvim_win_is_valid(win) then
			return nil
		end
		return rows[vim.api.nvim_win_get_cursor(win)[1]]
	end

	local function preview()
		local c = current()
		if
			not c
			or not vim.api.nvim_win_is_valid(code_win)
			or not vim.api.nvim_buf_is_valid(c.bufnr)
		then
			return
		end
		-- Guarded: switching the code window to another buffer can fail (E37) when
		-- its current buffer is modified and 'hidden' is off. Skip the preview
		-- rather than throw; the list stays usable.
		if not pcall(vim.api.nvim_win_set_buf, code_win, c.bufnr) then
			return
		end
		local line = math.min(c.start_line, math.max(1, vim.api.nvim_buf_line_count(c.bufnr)))
		vim.api.nvim_win_set_cursor(code_win, { line, 0 })
		vim.api.nvim_win_call(code_win, function()
			vim.cmd("normal! zz")
		end)
	end

	open_list = { win = win, buf = buf, render = render, dismiss = dismiss }

	render()
	preview()

	vim.api.nvim_create_autocmd("CursorMoved", { group = grp, buffer = buf, callback = preview })

	vim.api.nvim_create_autocmd("WinLeave", {
		group = grp,
		buffer = buf,
		callback = function()
			-- Navigating away without <CR> is a cancel. Deferred because a WinLeave callback is
			-- not allowed to close a window; skipped while the list is coming down on purpose,
			-- since restoring then would undo the jump <CR> just made.
			vim.schedule(function()
				if not closing then
					close()
				end
			end)
		end,
	})

	local function map(lhs, fn)
		vim.keymap.set("n", lhs, fn, { buffer = buf, nowait = true, silent = true })
	end

	map("q", close)
	map("<Esc>", close)
	-- <CR> is the jump: the preview already put the code window where the user wants it.
	map("<CR>", dismiss)
	map("e", function()
		local c = current()
		if c then
			handlers.edit(c, function()
				if render() then
					preview()
				end
			end)
		end
	end)
	-- No `nowait` here: `dd` needs the timeout to collect its second key, and binding the whole
	-- gesture keeps a stray `d` (the start of `dd`, `dw`, `diw`) from destroying a comment.
	vim.keymap.set("n", "dd", function()
		local c = current()
		if c then
			handlers.delete(c)
			if render() then
				preview()
			end
		end
	end, { buffer = buf, silent = true })
end

-- Redraw an open list from the live comment store. render() closes the window when nothing is
-- left, so clearing every comment both drops the list and puts the code window back.
function M.refresh_list()
	local list = open_list
	if not list then
		return
	end
	if not vim.api.nvim_win_is_valid(list.win) or not vim.api.nvim_buf_is_valid(list.buf) then
		open_list = nil
		return
	end
	list.render()
end

function M.pick_agent(agent_list, on_choice)
	if #agent_list == 0 then
		vim.notify("agent-comments: no herdr agents found", vim.log.levels.WARN)
		return
	end
	-- Pure selection: send-time policy (e.g. the "working" warning) lives in the
	-- caller's on_choice, so both the picker and the auto-resolve path share it.
	vim.ui.select(
		agent_list,
		{ prompt = "Send to agent", format_item = agents.display },
		function(a)
			if a then
				on_choice(a)
			end
		end
	)
end

return M
