return {
	name = "run py script",
	builder = function()
		local default_sh_full_path = vim.fn.expand("%:p")
		local cmd = { "python3", default_sh_full_path }

		local extra_args = vim.fn.input("\n\nCMD:" .. table.concat(cmd, " ") .. "\n\nArgs: ")
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
		filetype = { "python" },
	},
	priority = 2,
}
