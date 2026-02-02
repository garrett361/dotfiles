local c_and_cpp_utils = require("nvim_utils").prequire("overseer.utils.c_and_cpp_utils")
return {
	name = "clang++ compile",
	builder = function()
		local default_args = {
			"-std=c++20",
			"-march=native",
			"-Wall",
			"-O3",
		}
		local args = c_and_cpp_utils.args_generator(default_args, "cpp")

		return {
			cmd = { "clang++" },
			args = args,
			components = { "default" },
		}
	end,
	condition = {
		filetype = { "cpp" },
	},
	priority = 3,
}
