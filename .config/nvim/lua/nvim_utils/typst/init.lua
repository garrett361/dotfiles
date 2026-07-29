local M = {}

---Is the cursor in a math env?
---@return boolean
M.in_math_env = function()
	local captures = vim.treesitter.get_captures_at_cursor()
	local in_math_env = vim.tbl_contains(captures, "markup.math")
	return in_math_env
end

return M
