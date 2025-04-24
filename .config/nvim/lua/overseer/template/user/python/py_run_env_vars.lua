local function parse_env_vars(str)
	local result = {}
	for pair in str:gmatch("%S+") do
		local key, value = pair:match("([^=]+)=(.*)")
		if key and value then
			result[key] = value
		end
	end
	return result
end
return {
	name = "run py script with env vars",
	builder = function()
		local default_sh_full_path = vim.fn.expand("%:p")
		local cmd = { "python3", default_sh_full_path }

		local extra_args = vim.fn.input("\n\nCMD:" .. table.concat(cmd, " ") .. "\n\nArgs: ")
		if extra_args ~= "" then
			for a in extra_args:gmatch("%S+") do
				table.insert(cmd, a)
			end
		end

		local env_vars =
			vim.fn.input("\n\nCMD:" .. table.concat(cmd, " ") .. "\n\nEnv vars (space separated): ")
		local env_vars_table = {}
		if env_vars ~= "" then
			env_vars_table = parse_env_vars(env_vars)
		else
			env_vars_table = {}
		end

		return {
			cmd = cmd,
			args = {},
			env = env_vars_table,
			components = { { "on_output_quickfix", open = true }, "default" },
		}
	end,
	condition = {
		filetype = { "python" },
	},
	priority = 2,
}
