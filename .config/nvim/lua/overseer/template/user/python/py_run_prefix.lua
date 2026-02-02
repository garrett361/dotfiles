return {
	name = "run py script (pre- and postfix args)",
	builder = function()
		local default_sh_full_path = vim.fn.expand("%:p")
		local cmd = { "python3", default_sh_full_path }

		local prefix_args =
			vim.fn.input("\n\nCMD:" .. table.concat(cmd, " ") .. "\n\nPrefix Args: ")
		if prefix_args ~= "" then
			for a in prefix_args:gmatch("%S+") do
				table.insert(cmd, 1, a)
			end
		end
		local postfix_args =
			vim.fn.input("\n\nCMD:" .. table.concat(cmd, " ") .. "\n\nPostfix Args: ")
		if postfix_args ~= "" then
			for a in postfix_args:gmatch("%S+") do
				table.insert(cmd, a)
			end
		end

		return {
			cmd = cmd,
			args = {},
			components = { "default" },
		}
	end,
	condition = {
		filetype = { "python" },
	},
	priority = 2,
}
