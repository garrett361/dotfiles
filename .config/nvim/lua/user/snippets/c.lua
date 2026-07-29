local ls = require("nvim_utils").prequire("luasnip")

-- Helper objects, following the docs.
local s = ls.snippet
local sn = ls.snippet_node
local i = ls.insert_node
local c = ls.choice_node
local extras = require("luasnip.extras")
local m = extras.match
local fmt = require("luasnip.extras.fmt").fmt
local fmta = require("luasnip.extras.fmt").fmta

local snippets, autosnippets = {}, {}

-- Dynamic nodes -----------------------------------------------------------------

local include = {
	s(
		",i",
		fmt(
			[[#include {}]],
			{ c(1, { sn(1, fmt([[<{}>]], { i(1) })), sn(1, fmt([["{}"]], { i(1) })) }) }
		)
	),
	s(",u", fmta([[using <>::<>;]], { i(1), i(2) })),

	s(
		",m",
		fmta(
			[[
            int main(){
            <>
            }
        ]],
			{ i(1) }
		)
	),
}

local collection = { include }

for _, snip in pairs(collection) do
	autosnippets = vim.list_extend(autosnippets, snip)
end

return snippets, autosnippets
