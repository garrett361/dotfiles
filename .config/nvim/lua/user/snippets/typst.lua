local ls = require("nvim_utils").prequire("luasnip")
local typst_utils = require("nvim_utils.typst")

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

local function O_dynamic()
	if typst_utils.in_math_env() then
		return sn(nil, fmta([[cal(O)( <> )]], { i(1) }))
	else
		return sn(nil, fmta([[$cal(O)( <> )$]], { i(1) }))
	end
end

local function mono_dynamic()
	if typst_utils.in_math_env() then
		return sn(nil, fmta([[mono("<>")]], { i(1) }))
	else
		return sn(nil, fmta([[$mono("<>")$]], { i(1) }))
	end
end

local env = {
	s(
		",py",
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
        $
        <>
        $
        ]],
			{ i(1) }
		)
	),
	s(",,", fmta("$<>$", { i(1) })),
}

-- no stylua so that entries stay single-line and can be sorted more easily, to avoid duplication/overwriting
-- stylua: ignore start
local dot = {
	s(".a", fmta([[alpha]], {})),
	s(".b", fmta([[beta]], {})),
	s(".d", fmta([[delta]], {})),
	s(".D", fmta([[Delta]], {})),
	s(".e", fmta([[epsilon]], {})),
	s(".E", fmta([[eta]], {})),
	s(".g", fmta([[gamma]], {})),
	s(".h", fmta([[phi]], {})),
	s(".H", fmta([[Phi]], {})),
	s(".k", fmta([[kappa]], {})),
	s(".l", fmta([[lambda]], {})),
	s(".L", fmta([[Lambda]], {})),
	s(".m", fmta([[mu]], {})),
	s(".n", fmta([[nu]], {})),
	s(".o", fmta([[omega]], {})),
	s(".O", fmta([[Omega]], {})),
	s(".p", fmta([[pi]], {})),
	s(".P", fmta([[Pi]], {})),
	s(".r", fmta([[rho]], {})),
	s(".s", fmta([[sigma]], {})),
	s(".S", fmta([[Sigma]], {})),
	s(".t", fmta([[tau]], {})),
	s(".T", fmta([[theta]], {})),
-- stylua: ignore end
}

local comma = {
	s({ trig = ",*", wordTrig = false }, fmta([[times]], {}), { condition = typst_utils.in_math_env }),
	s({ trig = ",<<", wordTrig = false }, fmta([[angle.l]], {}), { condition = typst_utils.in_math_env }),
	s({ trig = ",<>", wordTrig = false }, fmta([[angle.l <> angle.r]], {i(1)}), { condition = typst_utils.in_math_env }),
	s({ trig = ",=", wordTrig = false }, t([[eq.triple]]), { condition = typst_utils.in_math_env }),
	s({ trig = ",>>", wordTrig = false }, fmta([[angle.r]], {}), { condition = typst_utils.in_math_env }),
	s({ trig = ",D", wordTrig = false }, fmta([[dot]], {}), { condition = typst_utils.in_math_env }),
	s({ trig = ",O", wordTrig = false }, d(1, O_dynamic)),
	s({ trig = ",d", wordTrig = false }, fmta("_( <> )", { i(1) }), { condition = typst_utils.in_math_env }),
	s({ trig = ",e", wordTrig = false }, fmta("e^( <> )", { i(1) }), { condition = typst_utils.in_math_env }),
	s({ trig = ",m", wordTrig = false }, d(1, mono_dynamic)),
	s({ trig = ",pd", wordTrig = false }, fmta([[partial]], {}), { condition = typst_utils.in_math_env }),
	s({ trig = ",u", wordTrig = false }, fmta("^( <> )", { i(1) }), { condition = typst_utils.in_math_env }),
	s({ trig = ",fn", wordTrig = false }, fmt("#footnote[{}]", { i(1) })),
}

local other = {
    -- Add the escape for primes in math mode
	s({ trig = "'", wordTrig = false }, fmt("\\'", {} ), { condition = typst_utils.in_math_env }),
}



local collection = { env, dot, comma, other}

for _, snip in pairs(collection) do
	autosnippets = vim.list_extend(autosnippets, snip)
end

return snippets, autosnippets
