local c_and_cpp_utils = require("nvim_utils").prequire("overseer.utils.c_and_cpp_utils")
return {
    name = "clang++ compile - debug",
    builder = function()
        -- Full path to current file (see :help expand())
        local default_args = {
            "-std=c++20",
            "-march=native",
            "-pedantic",
            "-Wall",
            "-Weffc++",
            "-Wextra",
            "-Wconversion",
            "-Wsign-conversion",
            "-g",
        }
        local args = c_and_cpp_utils.args_generator(default_args, "cpp")
        return {
            cmd = {
                "clang++",
            },
            args = args,
            components = { "default" },
        }
    end,
    condition = {
        filetype = { "cpp" },
    },
    priority = 1,
}
