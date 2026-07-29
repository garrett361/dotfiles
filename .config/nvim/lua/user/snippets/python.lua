local ls = require("nvim_utils").prequire("luasnip")

-- Helper objects, following the docs.
local s = ls.snippet
local i = ls.insert_node
local f = ls.function_node
local c = ls.choice_node
local extras = require("luasnip.extras")
local p = extras.partial
local m = extras.match
local fmta = require("luasnip.extras.fmt").fmta

local snippets, autosnippets = {}, {}

local py_method_node = fmta(
	[[
    def <>(self<>) ->> <>:
        <>
    ]],
	{ i(1), i(2), i(3), i(4) }
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
		{ i(1), i(2), i(3) }
	)
)
table.insert(autosnippets, py_class)

local py_init_node = fmta(
	[[
    def __init__(self<>) ->> None:
        <>
    ]],
	{ i(1), i(2) }
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
