local M = {}

---@param s string
---@return string[]
M.split_on_new_lines = function(s)
	local lines = {}
	for line in s:gmatch("[^\r\n]+") do
		table.insert(lines, line)
	end
	return lines
end

return M
