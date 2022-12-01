local utils = require("nvim_utils")

local M = {}

--- Returns an array of the capital letters currently used for global marks.
---@return string[]
M.get_global_marks = function()
	local marks = vim.fn.execute("marks")
	marks = vim.split(marks, "\n")

	local user_defined_marks = {}
	for i = #marks, 3, -1 do
		local mark = marks[i]:match("%s+(%u)%s+(.*)")
		if mark then
			table.insert(user_defined_marks, mark)
		end
	end

	table.sort(user_defined_marks, function(a, b)
		return a < b
	end)

	return user_defined_marks
end

local capital_letters = {}
for i = 65, 90 do
	table.insert(capital_letters, string.char(i))
end

---Get the next available capital letter to create a new global mark.
---@return string?
M.get_next_avail_global_mark = function()
	local current_global_marks = M.get_global_marks()
	for _, mark in ipairs(capital_letters) do
		if not require("nvim_utils.table").contains(current_global_marks, mark) then
			return mark
		end
	end
	vim.fn.input("No global marks available!")
	return
end

---Set the next available global mark at the current position.
M.set_next_avail_global_mark = function()
	local mark = M.get_next_avail_global_mark()
	if mark then
		local _, line, col, _ = unpack(vim.fn.getpos("."))
		vim.api.nvim_buf_set_mark(0, mark, line, col, {})
		vim.notify("Set global mark " .. mark)
	end
end

return M
