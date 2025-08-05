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

-- Returns a list of all unique files which are globally marked
M.get_global_mark_files = function()
	local marks = vim.fn.getmarklist()
	local file_paths = {}
	local seen_paths = {}

	for _, mark in ipairs(marks) do
		local mark_name = mark.mark:sub(2) -- Remove the ' prefix

		-- Check if it's a global mark (A-Z)
		if mark_name:match("^[A-Z]$") and mark.file and mark.file ~= "" then
			local file_path = vim.fn.fnamemodify(mark.file, ":p") -- Get absolute path

			-- Add to list if not already seen
			if not seen_paths[file_path] then
				seen_paths[file_path] = true
				table.insert(file_paths, file_path)
			end
		end
	end

	return file_paths
end

return M
