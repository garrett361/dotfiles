return {
	name = "cpp run",
	builder = function()
		-- Full path to current file (see :help expand())
		local default_binary_full_path = vim.fn.expand("%:p"):gsub("%.cpp", "")
		local pwd, default_binary_short = default_binary_full_path:match("(.*/)(.*)")
		local input_binary = vim.fn.input("Binary (default: " .. default_binary_short .. ") ")

		local cmd = {}
		if input_binary ~= "" then
			table.insert(cmd, pwd .. input_binary)
		else
			table.insert(cmd, default_binary_full_path)
		end

		local extra_args = vim.fn.input("Args: ")
		if extra_args ~= "" then
			for a in extra_args:gmatch("%S+") do
				table.insert(cmd, a)
			end
		end
		return {
			cmd = cmd,
			args = {},
			components = { { "on_output_quickfix", open = true }, "default" },
		}
	end,
	condition = {
		filetype = { "cpp" },
	},
	priority = 2,
}
