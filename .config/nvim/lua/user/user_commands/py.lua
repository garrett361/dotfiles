vim.api.nvim_create_user_command("Py", function(opts)
	local cmd = opts.args
	local result = vim.system({ "python", "-c", "import math; print(" .. cmd .. ")" }):wait()
	if result.code ~= 0 then
		require("nvim_utils").input_print(result)
		error("Error " .. result.stderr)
	end
	local result_text = result.stdout:gsub("[\n\r]", "")
	require("nvim_utils").insert_text_at_cursor(result_text)
end, {
	nargs = "+",
	desc = "Evaluate an arbitrary python command",
})
