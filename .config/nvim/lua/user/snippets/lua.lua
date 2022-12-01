local ls = require("nvim_utils").prequire("luasnip")

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

local prequire = s("pp", fmta("local <> = require('nvim_utils').prequire('<>')", { i(1), rep(1) }))
table.insert(autosnippets, prequire)

local fn = s(
	",f",
	fmta(
		[[
        local function <>(<>)
            <>
        end
]],
		{ i(1), i(2), i(3) }
	)
)
table.insert(autosnippets, fn)

local input_print = s(",p", fmta([[require("nvim_utils").input_print(<>)]], { i(1) }))
table.insert(autosnippets, input_print)

return snippets, autosnippets
