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

local py_method_node = fmta(
	[[
    def <>(self<>) ->> <>:
        <>
    ]],
	{ i(1), c(2, { sn(nil, { t(", "), i(1) }), t("") }), i(3), i(4) }
)

local py_method = s(",m", py_method_node)
table.insert(autosnippets, py_method)

local py_function = s(
	",f",
	fmta(
		[[
    def <>(<>) ->> <>:
        <>
    ]],
		{ i(1), i(2), i(3), i(4) }
	)
)
table.insert(autosnippets, py_function)

local py_class = s(
	",c",
	fmta(
		[[
    class <>:

        def __init__(self<>) ->> None:
            <>
    ]],
		{ i(1), c(2, { sn(nil, { t(", "), i(1) }), t("") }), i(3) }
	)
)
table.insert(autosnippets, py_class)

local py_init_node = fmta(
	[[
    def __init__(self<>) ->> None:
        <>
    ]],
	{ c(1, { sn(nil, { t(", "), i(1) }), t("") }), i(2) }
)

local py_init = s(",i", py_init_node)
table.insert(autosnippets, py_init)

local py_print_node = fmta([[print("<>")]], { i(1) })

local py_print = s(",p", py_print_node)

table.insert(autosnippets, py_print)

local py_multiline_comment = s(
	",C",
	fmta(
		[[
        """
        <>
        """
    ]],
		{ i(1) }
	)
)
table.insert(autosnippets, py_multiline_comment)

local if_name_main = s(
	"inm",
	fmta(
		[[
if __name__ == "__main__":
    <>
 ]],
		{ i(1) }
	)
)
table.insert(autosnippets, if_name_main)

return snippets, autosnippets
