local function copy_path(path_expr)
	vim.fn.setreg("+", vim.fn.expand(path_expr))
end

local function copy_path_with_loc(path_expr)
	local path = vim.fn.expand(path_expr)
	local start_line = vim.fn.line("v")
	local end_line = vim.fn.line(".")

	if start_line > end_line then
		start_line, end_line = end_line, start_line
	end

	local result = start_line == end_line and path .. ":" .. start_line
		or path .. ":" .. start_line .. "-" .. end_line
	vim.fn.setreg("+", result)
end

-- Copy relative path to system clipboard
vim.api.nvim_create_user_command("CopyPath", function()
	copy_path("%:.")
end, {})
-- Copy full/absolute path to system clipboard
vim.api.nvim_create_user_command("CopyPathFull", function()
	copy_path("%:p")
end, {})
-- Copy relative path as Python module notation (e.g., foo/bar.py -> foo.bar)
vim.api.nvim_create_user_command(
	"CopyPathPy",
	'let @+=substitute(substitute(expand("%:.:r"), "/", ".", "g"), "^\\\\.", "", "")',
	{}
)

vim.keymap.set("n", "<leader>yy", function()
	copy_path("%:.")
end, { desc = "Copy relative path to clipboard" })
vim.keymap.set("x", "<leader>yy", function()
	copy_path_with_loc("%:.")
end, { desc = "Copy relative path with lines to clipboard" })
vim.keymap.set("n", "<leader>yp", ":CopyPathPy<CR>", { desc = "Copy Python path to clipboard" })
vim.keymap.set("n", "<leader>yf", function()
	copy_path("%:p")
end, { desc = "Copy absolute path to clipboard" })
vim.keymap.set("x", "<leader>yf", function()
	copy_path_with_loc("%:p")
end, { desc = "Copy absolute path with lines to clipboard" })
