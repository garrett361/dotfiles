M = {}

---Expand ~ to the home dir
---@param path string
---@return string
M.expand_tilde = function(path)
	local expanded = path:gsub("^~", vim.fn.expand("~"))
	return expanded
end

---Return just the file name, given a full path
---@param path string
---@return string
M.get_file_name = function(path)
	local full_path = vim.fn.expand(path)
	local file_name = vim.fn.fnamemodify(full_path, ":t")
	return file_name
end

---@param directory string
---@param file_names_only boolean Default: true
---@param pattern? string lua regex pattern to match the full path against
---@return string[]
M.get_files_in_directory = function(directory, file_names_only, pattern)
	if file_names_only ~= false then
		file_names_only = true
	end

	-- Get all files and directories in the specified directory
	local glob_path = M.expand_tilde(directory) .. "/*"
	local files_string = vim.fn.glob(glob_path)

	-- Split the string into a table
	local full_path_files_table = vim.split(files_string, "\n")

	-- Filter out directories and optionally only return file names
	local files_table = {}
	for _, file in ipairs(full_path_files_table) do
		if vim.fn.isdirectory(file) == 0 then
			if pattern ~= nil and not string.match(file, pattern) then
				goto continue
			end
			if file_names_only then
				file = M.get_file_name(file)
			end
			table.insert(files_table, file)
		end
		::continue::
	end

	return files_table
end

return M
