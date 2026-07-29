local M = {}

---Check if two tables are equal
---@param t1 table
---@param t2 table
---@return boolean
M.equal = function(t1, t2)
	-- Check if the tables have the same number of elements
	if #t1 ~= #t2 then
		return false
	end

	-- Iterate through t1 and check if each key-value pair exists in t2
	for k, v in pairs(t1) do
		if t2[k] ~= v then
			return false
		end
	end

	-- If all checks pass, the tables are equal
	return true
end

---Check whether a table contains the given element
---@param t table
---@param element any
---@return boolean
M.contains = function(t, element)
	for _, value in ipairs(t) do
		if value == element then
			return true
		end
	end
	return false
end

---Check whether a table contains the given element
---@param t string[]
---@param pattern string
---@return string[]
M.filter_by_pattern = function(t, pattern)
	local ret = {}
	for _, value in ipairs(t) do
		if value:match(pattern) then
			table.insert(ret, value)
		end
	end
	return ret
end

---@param t string[]
---@param indent integer
---@param visited table<table, boolean>
---@return string
M.table_to_string = function(t, indent, visited)
	if type(t) ~= "table" then
		return tostring(t)
	end

	visited = visited or {}
	indent = indent or 0

	if visited[t] then
		return "{ ... }" -- Circular reference
	end
	visited[t] = true

	local result = {}
	local padding = string.rep("  ", indent)

	for k, v in pairs(t) do
		local key = type(k) == "string" and '["' .. k .. '"]' or "[" .. tostring(k) .. "]"
		local value = type(v) == "table" and M.table_to_string(v, indent + 1, visited)
			or tostring(v)
		table.insert(result, padding .. "  " .. key .. " = " .. value)
	end

	return "{\n" .. table.concat(result, ",\n") .. "\n" .. padding .. "}"
end

return M
