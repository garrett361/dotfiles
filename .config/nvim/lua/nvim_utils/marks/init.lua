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
		if not vim.tbl_contains(current_global_marks, mark) then
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

-- Returns a map from global marks to their file paths.
M.get_global_mark_files = function()
	local marks = vim.fn.getmarklist()
	local mark_to_file = {}

	-- Create a map of all available marks first
	local available_marks = {}
	for _, mark in ipairs(marks) do
		local mark_name = mark.mark:sub(2) -- Remove the ' prefix
		if mark_name:match("^[A-Z]$") and mark.file and mark.file ~= "" then
			available_marks[mark_name] = vim.fn.fnamemodify(mark.file, ":p")
		end
	end

	-- Build result dictionary in alphabetical order A-Z
	for i = string.byte("A"), string.byte("Z") do
		local mark_name = string.char(i)
		if available_marks[mark_name] then
			mark_to_file[mark_name] = available_marks[mark_name]
		end
	end

	return mark_to_file
end

M.get_first_global_mark_in_current_file = function()
	local current_file_path = vim.fn.fnamemodify(vim.fn.expand("%"), ":p")
	local mark_to_file = M.get_global_mark_files()

	-- Since marks are processed A-Z, first match is alphabetically first
	for mark_name, file_path in pairs(mark_to_file) do
		if file_path == current_file_path then
			return mark_name
		end
	end

	return nil
end

M.update_or_set_global_mark = function()
	local existing_mark = M.get_first_global_mark_in_current_file()
	if existing_mark then
		-- Update the existing mark to current position
		local _, line, col, _ = unpack(vim.fn.getpos("."))
		vim.api.nvim_buf_set_mark(0, existing_mark, line, col, {})
		vim.notify("Updated global mark " .. existing_mark)
	else
		-- No mark exists, create a new one
		M.set_next_avail_global_mark()
	end
end

return M
