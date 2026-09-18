local prompt = require("agent-comments.prompt")

T.test("prompt: single comment renders as path, range, quoted line, comment", function()
	local s = prompt.format({
		{
			comment = {
				file = "/tmp/x.py",
				start_line = 5,
				end_line = 5,
				text = "rename to double",
			},
			snippet = { "def f(x): return x*2" },
		},
	}, {})
	local expected = table.concat({
		"1 comment:",
		"",
		"1. /tmp/x.py:5-5",
		"   5 | def f(x): return x*2",
		"   Comment: rename to double",
	}, "\n")
	T.eq(s, expected)
	T.ok(not s:find("End of comments", 1, true), "no footer terminates the message")
	T.ok(s:sub(-1) ~= "\n", "the message ends with the last Comment line, not a blank line")
end)

T.test("prompt: the header counts the items and pluralises", function()
	local one = prompt.format({
		{
			comment = { file = "a.lua", start_line = 1, end_line = 1, text = "c1" },
			snippet = { "a" },
		},
	})
	T.ok(one:find("1 comment:", 1, true) == 1)

	local two = prompt.format({
		{
			comment = { file = "a.lua", start_line = 1, end_line = 1, text = "c1" },
			snippet = { "a" },
		},
		{
			comment = { file = "b.lua", start_line = 1, end_line = 1, text = "c2" },
			snippet = { "b" },
		},
	})
	T.ok(two:find("2 comments:", 1, true) == 1)
end)

T.test("prompt: multiple comments numbered, whole snippet quoted", function()
	local s = prompt.format({
		{
			comment = { file = "a.rs", start_line = 1, end_line = 5, text = "c1" },
			snippet = { "l1", "l2", "l3", "l4", "l5" },
		},
		{
			comment = { file = "b.rs", start_line = 2, end_line = 3, text = "c2" },
			snippet = { "x", "y" },
		},
	})
	T.ok(s:find("2 comments:", 1, true) == 1)
	T.ok(s:find("\n1. a.rs:1-5\n", 1, true), "the header ends at the range, with no parenthetical")
	T.ok(s:find("\n   3 | l3\n", 1, true))
	T.ok(s:find("\n   5 | l5\n", 1, true), "the whole snippet must be quoted, not capped at 3")
	T.ok(not s:find("omitted", 1, true), "an uncapped snippet must not claim omissions")
	T.ok(s:find("\n2. b.rs:2-3\n", 1, true), "the header ends at the range, with no parenthetical")
	T.ok(s:find("   Comment: c2", 1, true))
end)

T.test("prompt: a capped snippet names the omitted count and true end line", function()
	local s = prompt.format({
		{
			comment = { file = "big.lua", start_line = 10, end_line = 14, text = "too long" },
			snippet = { "a", "b", "c", "d", "e" },
		},
	}, { max_snippet_lines = 2 })
	T.ok(s:find("\n   10 | a\n   11 | b\n", 1, true), "the cap's worth of lines is quoted")
	T.ok(not s:find("| c", 1, true), "lines past the cap are not quoted")
	T.ok(
		s:find(
			"\n   ... 3 more line(s) omitted, through line 14; read the file for the rest\n",
			1,
			true
		),
		"truncation is announced with the count and the true end line"
	)
end)

T.test("prompt: quoted line numbers count up from start_line", function()
	local s = prompt.format({
		{
			comment = { file = "m.lua", start_line = 100, end_line = 101, text = "note" },
			snippet = { "x", "y" },
		},
	})
	T.ok(s:find("\n   100 | x\n   101 | y\n", 1, true))
	T.ok(not s:find("   1 | x", 1, true), "numbering must not restart at 1")
end)

T.test("prompt: line numbers stay right-aligned when their width grows mid-item", function()
	local s = prompt.format({
		{
			comment = { file = "w.lua", start_line = 9, end_line = 11, text = "widths" },
			snippet = { "nine", "", "eleven" },
		},
	})
	T.ok(s:find("\n    9 | nine\n   10 |\n   11 | eleven\n", 1, true))
end)

T.test("prompt: unsaved items are marked and explained, saved-only items are not", function()
	local unsaved = prompt.format({
		{
			comment = {
				file = "u.lua",
				start_line = 1,
				end_line = 1,
				text = "wip",
				modified = true,
			},
			snippet = { "draft" },
		},
	})
	T.ok(unsaved:find("1. u.lua:1-1 [unsaved]", 1, true), "a modified comment is marked")
	T.ok(unsaved:find("Items marked [unsaved] quote my editor buffer", 1, true))

	local saved = prompt.format({
		{
			comment = { file = "s.lua", start_line = 1, end_line = 1, text = "ok" },
			snippet = { "final" },
		},
	})
	T.ok(not saved:find("[unsaved]", 1, true), "an unmodified comment is not marked")
	T.ok(not saved:find("not yet written to disk", 1, true), "no preamble without unsaved items")
end)
