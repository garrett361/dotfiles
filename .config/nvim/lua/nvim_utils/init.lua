local M = {}

--- @alias bufnum integer
--- @alias lnum integer
--- @alias col integer
--- @alias off  integer
--- @alias cursor_pos [bufnum, lnum, col, off]

--- Provide a status message for which module failed to load
--- @param module_name string
--- @return any
M.prequire = function(module_name)
	local status_ok, module = pcall(require, module_name)
	assert(status_ok, "Error loading module " .. module_name)
	return module
end

M.is_visual_mode = function()
	local current_mode = vim.fn.mode()
	-- '\22' is visual block mode
	return current_mode == "v" or current_mode == "V" or current_mode == "\22"
end

---Feed keys to neovim
---@param str string
---@param mode string?
M.feedkeys = function(str, mode)
	mode = mode or "n"
	local keys = vim.api.nvim_replace_termcodes(str, true, true, true)
	vim.api.nvim_feedkeys(keys, mode, false)
end

--- From nvim-dap: split string into args, respecting bash groupings
--- @param str string
--- @return string[]
function M.string_to_args(str)
	local lpeg = vim.lpeg
	local P, S, C = lpeg.P, lpeg.S, lpeg.C

	---@param quotestr string
	---@return vim.lpeg.Pattern
	local function qtext(quotestr)
		local quote = P(quotestr)
		local escaped_quote = P("\\") * quote
		return quote * C(((1 - P(quote)) + escaped_quote) ^ 0) * quote
	end

	local space = S(" \t\n\r") ^ 1
	local unquoted = C((1 - space) ^ 0)
	local element = qtext('"') + qtext("'") + unquoted
	local p = lpeg.Ct(element * (space * element) ^ 0)
	return lpeg.match(p, str)
end

--- Print and pause for input
---@param obj any
---@return string
function M.input_print(obj)
	local input = vim.fn.input(tostring(vim.inspect(obj)) .. "\n")
	return input
end

---Slice a table. Zero-indexed, with python-like syntax.
---@param tbl table
---@param start integer
---@param stop integer?
---@return table
function M.slice(tbl, start, stop)
	stop = stop or #tbl
	if stop == -1 then
		stop = #tbl - 1
	end
	assert(start <= stop)

	local sliced = {}
	for i = start + 1, stop do
		table.insert(sliced, tbl[i])
	end
	return sliced
end

---Gets the *current* visual start and stop locations
---@return [cursor_pos, cursor_pos]
function M.get_vis_pos()
	local start = nil
	local stop = nil
	if M.is_visual_mode() then
		--- Currently in some visual mode
		start = vim.fn.getpos("v")
		stop = vim.fn.getpos(".")
	else
		--- Just left visual mode
		start = vim.fn.getpos("'<")
		stop = vim.fn.getpos("'>")
	end

	local _, start_line, start_col, _ = unpack(start)
	local _, stop_line, stop_col, _ = unpack(stop)
	if start_line > stop_line or (stop_line == start_line and stop_col < start_col) then
		start, stop = stop, start
	end
	return { start, stop }
end

---Gets the *current* visually selected text
---@param replace_termcodes? boolean
---@return string
function M.get_vis_text(replace_termcodes)
	local start, stop = unpack(M.get_vis_pos())
	local _, start_line, start_col, _ = unpack(start)
	local _, stop_line, stop_col, _ = unpack(stop)

	local lines = vim.api.nvim_buf_get_lines(0, start_line - 1, stop_line, false)
	if #lines == 1 then
		lines[1] = string.sub(lines[1], start_col, stop_col)
	else
		lines[1] = string.sub(lines[1], start_col)
		lines[#lines] = string.sub(lines[#lines], 1, stop_col)
	end

	local text = table.concat(lines, "\n")
	if replace_termcodes then
		text = vim.api.nvim_replace_termcodes(text, true, true, true)
	end
	return text
end

M.insert_text_at_cursor = function(text)
	local buf, row, col, _ = unpack(vim.fn.getpos("."))
	vim.api.nvim_buf_set_text(buf, row - 1, col, row - 1, col, { text })
end

---@return integer[]
M.get_visible_buffers = function()
    local visible_buffers = {}
    local seen_buffers = {}

    -- Get windows only from the current tabpage
    local current_tabpage = vim.api.nvim_get_current_tabpage()
    local windows = vim.api.nvim_tabpage_list_wins(current_tabpage)

    for _, win in ipairs(windows) do
        local win_config = vim.api.nvim_win_get_config(win)

        -- Skip floating windows
        if win_config.relative == "" then
            -- Check if window has visible area (not minimized)
            local height = vim.api.nvim_win_get_height(win)
            local width = vim.api.nvim_win_get_width(win)

            if height > 0 and width > 0 then
                local buf = vim.api.nvim_win_get_buf(win)
                if not seen_buffers[buf] then
                    seen_buffers[buf] = true
                    table.insert(visible_buffers, buf)
                end
            end
        end
    end

    return visible_buffers
end

return M
