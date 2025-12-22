local ls = require("nvim_utils").prequire("luasnip")
local tex_utils = require("nvim_utils").prequire("user.tex_utils")

-- Helper objects, following the docs.
local s = ls.snippet
local sn = ls.snippet_node
local isn = ls.indent_snippet_node
local t = ls.text_node
local i = ls.insert_node
local f = ls.function_node
local c = ls.choice_node
local d = ls.dynamic_node
local r = ls.restore_node
local events = require("luasnip.util.events")
local ai = require("luasnip.nodes.absolute_indexer")
local extras = require("luasnip.extras")
local l = extras.lambda
local rep = extras.rep
local p = extras.partial
local m = extras.match
local n = extras.nonempty
local dl = extras.dynamic_lambda
local fmt = require("luasnip.extras.fmt").fmt
local fmta = require("luasnip.extras.fmt").fmta
local conds = require("luasnip.extras.expand_conditions")
local postfix = require("luasnip.extras.postfix").postfix
local types = require("luasnip.util.types")
local parse = require("luasnip.util.parser").parse_snippet
local ms = ls.multi_snippet

local snippets, autosnippets = {}, {}

local env = {
	s(",l", fmta("[<>](<>)", { i(1), i(2) })),
	s(
		",p",
		fmta(
			[[
        ```python
        <>
        ```
        ]],
			{ i(1) }
		)
	),
	s(
		",b",
		fmta(
			[[
        ```bash
        <>
        ```
        ]],
			{ i(1) }
		)
	),
	s(
		",c",
		fmta(
			[[
        ```
        <>
        ```
        ]],
			{ i(1) }
		)
	),
	s(
		",a",
		fmta(
			[[
        $$
        <>
        $$
        ]],
			{ i(1) }
		)
	),
	s(",,", fmta("$<>$", { i(1) })),
	s(",ll", fmta([[\left ]], {})),
	s(",lr(", fmta([[\left ( <> \right ]], { i(1) })),
	s(",lr[", fmta([[\left [ <> \right ]], { i(1) })),
	s(",lr{", fmta([[\left \{ <> \right \]], { i(1) })),
	s(",rr", fmta([[\right ]], {})),
	s(",tt", fmta([[\texttt{<>}]], { i(1) })),
}

local math = {
	s(",d", fmta("_{ <> }", { i(1) })),
	s(",u", fmta("^{ <> }", { i(1) })),
	s(",ee", fmta("e^{ <> }", { i(1) })),
	s(",ff", fmta("\\frac{ <> }{ <> }", { i(1), i(2) })),
	s(",xx", t([[\exp ]])),
}

local collection = { env, math }

for _, snip in pairs(collection) do
	autosnippets = vim.list_extend(autosnippets, snip)
end

return snippets, autosnippets
