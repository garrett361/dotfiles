local function copy_path(path_expr, message)
	vim.fn.setreg("+", vim.fn.expand(path_expr))
	vim.api.nvim_echo({ { message } }, false, {})
end

local function copy_path_with_loc(path_expr, message)
	local path = vim.fn.expand(path_expr)
	local start_line = vim.fn.line("v")
	local end_line = vim.fn.line(".")

	if start_line > end_line then
		start_line, end_line = end_line, start_line
	end

	local result = start_line == end_line and path .. ":" .. start_line
		or path .. ":" .. start_line .. "-" .. end_line
	vim.fn.setreg("+", result)
	vim.api.nvim_echo({ { message } }, false, {})
	vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes("<Esc>", true, false, true), "n", false)
end

-- Copy relative path to system clipboard
vim.api.nvim_create_user_command("CopyPath", function()
	copy_path("%:.", "Path copied!")
end, {})
-- Copy full/absolute path to system clipboard
vim.api.nvim_create_user_command("CopyPathFull", function()
	copy_path("%:p", "Full path copied!")
end, {})
-- Copy relative path as Python module notation (e.g., foo/bar.py -> foo.bar)
vim.api.nvim_create_user_command(
	"CopyPathPy",
	'let @+=substitute(substitute(expand("%:.:r"), "/", ".", "g"), "^\\\\.", "", "")',
	{}
)

vim.keymap.set("n", "<leader>y", function()
	copy_path("%:.", "Path copied!")
end, { desc = "Copy relative path to clipboard" })
vim.keymap.set("x", "<leader>y", function()
	copy_path_with_loc("%:.", "Path copied!")
end, { desc = "Copy relative path with lines to clipboard" })
vim.keymap.set("n", "<leader>Y", function()
	copy_path("%:p", "Full path copied!")
end, { desc = "Copy absolute path to clipboard" })

vim.keymap.set("x", "<leader>Y", function()
	copy_path_with_loc("%:p", "Full path copied!")
end, { desc = "Copy absolute path with lines to clipboard" })
