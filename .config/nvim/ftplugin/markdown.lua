-- Buffer-local mapping options
local opts = { noremap = true, silent = true, buffer = 0 }

local function md_url_paste()
	-- Get clipboard
	local clip = vim.fn.getreg("+")
	-- 0-indexed locations
	local start_line = vim.fn.getpos("v")[2] - 1
	local start_col = vim.fn.getpos("v")[3] - 1
	local stop_line = vim.fn.getcurpos("")[2] - 1
	local stop_col = vim.fn.getcurpos("")[3] - 1
	-- Check start and stop aren't reversed, and swap if necessary
	if stop_line < start_line or (stop_line == start_line and stop_col < start_col) then
		start_line, start_col, stop_line, stop_col = stop_line, stop_col, start_line, start_col
	end
	-- Paste clipboard contents as md link.
	vim.api.nvim_buf_set_text(
		0,
		stop_line,
		stop_col + 1,
		stop_line,
		stop_col + 1,
		{ "](" .. clip .. ")" }
	)
	vim.api.nvim_buf_set_text(0, start_line, start_col, start_line, start_col, { "[" })
end
vim.keymap.set("v", "<leader>p", md_url_paste, opts)

-- Line wrapping cfg 
vim.bo.textwidth = 0
vim.opt_local.formatoptions:remove({ "t" })
vim.wo.wrap = true  -- Enable visual wrapping (optional)

-- -- Swap slash/backslash for latex
vim.keymap.set("i", "\\", "/", opts)
vim.keymap.set("i", "/", "\\", opts)
