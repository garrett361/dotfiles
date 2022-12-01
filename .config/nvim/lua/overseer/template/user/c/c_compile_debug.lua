local c_and_cpp_utils = require("nvim_utils").prequire("overseer.utils.c_and_cpp_utils")
return {
	name = "gcc compile - debug",
	builder = function()
		-- Full path to current file (see :help expand())
		local default_args = {
			"-std=c99",
			"-pedantic",
			"-Wall",
			"-Weffc++",
			"-Wextra",
			"-Wconversion",
			"-Wsign-conversion",
			"-g",
		}
		local args = c_and_cpp_utils.args_generator(default_args, "c")
		return {
			cmd = {
				"gcc",
			},
			args = args,
			components = { { "on_output_quickfix", open = true }, "default" },
		}
	end,
	condition = {
		filetype = { "c" },
	},
	priority = 1,
}
