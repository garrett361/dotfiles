local c_and_cpp_utils = require("nvim_utils").prequire("overseer.utils.c_and_cpp_utils")
return {
	name = "clang++ compile - save temps",
	builder = function()
		local default_args = {
			"-std=c++20",
			"-march=native",
			"-pedantic",
			"-Wall",
			"-Weffc++",
			"-Wextra",
			"-Wconversion",
			"-Wsign-conversion",
			"--save-temps=obj",
			"-g",
		}

		local args = c_and_cpp_utils.args_generator(default_args, "cpp")
		return {
			cmd = {
				"clang++",
			},
			args = args,
			components = { { "on_output_quickfix", open = true }, "default" },
		}
	end,
	condition = {
		filetype = { "cpp" },
	},
}
