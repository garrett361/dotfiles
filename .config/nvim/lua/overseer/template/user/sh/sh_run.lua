return {
	name = "run sh script",
	builder = function()
		local default_sh_full_path = vim.fn.expand("%:p")
		local cmd = { default_sh_full_path }

		local extra_args = vim.fn.input("Args: ")
		if extra_args ~= "" then
			for a in extra_args:gmatch("%S+") do
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
		filetype = { "sh" },
	},
	priority = 2,
}
