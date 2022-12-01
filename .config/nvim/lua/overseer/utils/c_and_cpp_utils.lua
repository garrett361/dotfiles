local M = {}

-- Helper for getting common source/binary file default names and inserting args
M.args_generator = function(default_args, file_suffix)
	local args = {}
	for _, a in ipairs(default_args) do
		table.insert(args, a)
	end
	local pwd = vim.fn.expand("%:h") .. "/"
	local c_files_table =
		vim.split(vim.fn.glob(pwd .. "*." .. file_suffix), "\n", { trimempty = true })
	local files_table_short = {}
	local files_table_full = {}
	for _, file in ipairs(c_files_table) do
		for _, short_f in string.gmatch(file, "(.*)/(.*)") do
			table.insert(files_table_short, short_f)
			table.insert(files_table_full, pwd .. short_f)
		end
	end

	local default_binary_name = vim.fn.expand("%:t"):gsub("%." .. file_suffix, "")
	local input_files =
		vim.fn.input("Files (default: " .. table.concat(files_table_short, " ") .. ") ")
	local input_binary = vim.fn.input("Binary (default: " .. default_binary_name .. ") ")

	if input_files ~= "" then
		for f in input_files:gmatch("%S+") do
			table.insert(args, pwd .. f)
		end
	else
		for _, file in ipairs(files_table_full) do
			table.insert(args, file)
		end
	end

	table.insert(args, "-o")
	if input_binary ~= "" then
		table.insert(args, pwd .. input_binary)
	else
		table.insert(args, pwd .. default_binary_name)
	end
	return args
end

return M
