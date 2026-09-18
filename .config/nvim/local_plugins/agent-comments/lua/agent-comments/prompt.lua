local M = {}

-- Line-number-prefixed quoting (`  13 | code`) rather than `> code`: the receiving agent has to
-- map each quoted line back to a position in the file, and counting down from a range header is
-- the step it gets wrong. Source tabs pass through verbatim, so a quoted line stays byte-identical
-- to the file and a patch built from it does not corrupt indentation.
local MAX_SNIPPET_LINES = 200

function M.format(items, opts)
	opts = opts or {}
	local max = opts.max_snippet_lines or MAX_SNIPPET_LINES

	local any_unsaved = false
	for _, item in ipairs(items) do
		if item.comment.modified then
			any_unsaved = true
		end
	end

	local lines = {
		string.format("%d comment%s:", #items, #items == 1 and "" or "s"),
	}
	if any_unsaved then
		table.insert(
			lines,
			"Items marked [unsaved] quote my editor buffer, which holds changes not yet written to disk."
		)
	end

	for i, item in ipairs(items) do
		table.insert(lines, "")
		local c = item.comment
		local head = string.format("%d. %s:%d-%d", i, c.file, c.start_line, c.end_line)
		if c.modified then
			head = head .. " [unsaved]"
		end
		table.insert(lines, head)

		local snippet = item.snippet or {}
		local shown = math.min(max, #snippet)
		local width = #tostring(c.start_line + math.max(shown, 1) - 1)
		for j = 1, shown do
			if snippet[j] == "" then
				table.insert(lines, string.format("   %" .. width .. "d |", c.start_line + j - 1))
			else
				table.insert(
					lines,
					string.format("   %" .. width .. "d | %s", c.start_line + j - 1, snippet[j])
				)
			end
		end
		if #snippet > shown then
			table.insert(
				lines,
				string.format(
					"   ... %d more line(s) omitted, through line %d; read the file for the rest",
					#snippet - shown,
					c.end_line
				)
			)
		end
		table.insert(lines, "   Comment: " .. c.text)
	end

	return table.concat(lines, "\n")
end

return M
