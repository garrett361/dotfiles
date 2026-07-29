local ls = require("nvim_utils").prequire("luasnip")

-- Helper objects, following the docs.
local s = ls.snippet
local i = ls.insert_node
local f = ls.function_node
local extras = require("luasnip.extras")
local rep = extras.rep
local p = extras.partial
local fmta = require("luasnip.extras.fmt").fmta

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
