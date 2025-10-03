function csv_to_markdown()
	-- Get the visually selected text
	local start_pos = vim.fn.getpos("'<")
	local end_pos = vim.fn.getpos("'>")
	local lines = vim.fn.getline(start_pos[2], end_pos[2])

	local markdown_lines = {}

	for i, line in ipairs(lines) do
		-- Split by comma, preserving empty fields
		local fields = {}
		-- Add trailing comma to catch final field, then match everything up to each comma
		for field in (line .. ","):gmatch("([^,]*),") do
			table.insert(fields, field)
		end

		-- Convert to markdown row
		local md_row = "|" .. table.concat(fields, "|") .. "|"
		table.insert(markdown_lines, md_row)

		-- Add separator row after header (first row)
		if i == 1 then
			local separator_parts = {}
			for j = 1, #fields do
				table.insert(separator_parts, "---")
			end
			local separator = "|" .. table.concat(separator_parts, "|") .. "|"
			table.insert(markdown_lines, separator)
		end
	end

	-- Insert blank line and markdown table after the selected lines
	vim.fn.append(end_pos[2], "")
	for i, md_line in ipairs(markdown_lines) do
		vim.fn.append(end_pos[2] + i, md_line)
	end
end

-- Create the user command
vim.api.nvim_create_user_command("CSVToMD", csv_to_markdown, { range = true })
