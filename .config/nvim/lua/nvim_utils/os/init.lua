local M = {}

---List files (not directories) directly under a directory.
---@param directory string
---@param file_names_only boolean? Default: true
---@param pattern? string lua regex pattern to match the full path against
---@return string[]
M.get_files_in_directory = function(directory, file_names_only, pattern)
	local paths = vim.fn.glob(vim.fs.normalize(directory) .. "/*", false, true)
	return vim.iter(paths)
		:filter(function(path)
			return vim.fn.isdirectory(path) == 0 and (pattern == nil or path:match(pattern))
		end)
		:map(function(path)
			return file_names_only == false and path or vim.fs.basename(path)
		end)
		:totable()
end

return M
