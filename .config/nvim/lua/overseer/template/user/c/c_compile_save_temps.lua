local c_and_cpp_utils = require("nvim_utils").prequire("overseer.utils.c_and_cpp_utils")
return {
	name = "gcc compile - save temps",
	builder = function()
		local default_args = {
			"-std=c99",
			"-pedantic",
			"-Wall",
			"-Weffc++",
			"-Wextra",
			"-Wconversion",
			"-Wsign-conversion",
			"--save-temps=obj",
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
}
