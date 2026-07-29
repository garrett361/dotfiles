-- Overseer's builtin cargo template covers build/run/test/clippy/fmt, but none of its entries
-- prompt for runtime args.
return {
	name = "run cargo bin with args",
	builder = function()
		local cmd = { "cargo", "run", "--" }

		local extra_args = vim.fn.input("\n\nCMD:" .. table.concat(cmd, " ") .. "\n\nArgs: ")
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
		filetype = { "rust" },
	},
	priority = 2,
}
