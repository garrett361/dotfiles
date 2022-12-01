return {
	name = "torchrun",
	builder = function()
		local default_sh_full_path = vim.fn.expand("%:p")
		local cmd = { "torchrun", "--nproc-per-node" }

		local world_size = vim.fn.input("\n\nWORLD_SIZE (default 2):")
		if world_size == "" then
			world_size = "2"
		end

		table.insert(cmd, world_size)
		table.insert(cmd, default_sh_full_path)

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
