-- FilterBelow passes the visually selected lines to arbitrary external fucntions. E.g. `FilterBelow diagon Math`
-- to generate ASCII math from the visual selection. Output is put into the buffer below the visual
-- selection
vim.api.nvim_create_user_command("FilterBelow", function(opts)
	local lines_table = vim.api.nvim_buf_get_lines(0, opts.line1 - 1, opts.line2, true)
	local lines_text = table.concat(lines_table, "\n")
	local cmd_output = vim.fn.system(opts.args .. " -- " .. vim.fn.shellescape(lines_text))
	local cmd_output_split = vim.fn.split(cmd_output, "\n")
	table.insert(cmd_output_split, 1, "") -- Insert a blank line to separate output
	vim.api.nvim_buf_set_lines(0, opts.line2, opts.line2, true, cmd_output_split)
end, { nargs = "?", range = true })
