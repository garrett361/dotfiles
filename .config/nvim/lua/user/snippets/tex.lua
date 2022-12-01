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

-- Dynamic nodes -----------------------------------------------------------------

-- nn is used to create new entries in various environments, such as align math environments
-- or itemized lists
local nn_in_align_node = fmta(
	[[
    \nn
    <> &= <>
    ]],
	{ i(1), i(2) }
)

local nn_in_itemize_node = fmta([[\item <>]], { i(1) })

local function nn_dynamic()
	if tex_utils.in_mathzone() then
		return sn(nil, nn_in_align_node)
	elseif tex_utils.in_itemize() or tex_utils.in_enumerate() then
		return sn(nil, { t({ "", "" }), sn(1, nn_in_itemize_node) })
	else
		return sn(nil, t("nn"))
	end
end

local function bb_dynamic()
	if tex_utils.in_mathzone() then
		return sn(nil, fmta([[\mathbf{<>}]], { i(1) }))
	else
		return sn(nil, fmta([[\textbf{<>}]], { i(1) }))
	end
end

-- Snippets -----------------------------------------------------------------

local env = {
	s(
		",a",
		fmta(
			[[
        \begin{align}
            <> &= <>
        \end{align}
        ]],
			{ i(1), i(2) }
		)
	),
	s(
		",PM",
		fmta(
			[[
        \begin{pmatrix}
            <>
        \end{pmatrix}
        ]],
			{ i(1) }
		)
	),
	s(
		",E",
		fmta(
			[[
    \begin{enumerate}
        \item <>
    \end{enumerate}
    ]],
			{ i(1) }
		)
	),
	s(
		",FF",
		fmta(
			[[
\begin{figure}[ht]
    \centering
    \includegraphics<>{<>}
    \caption{<>}
    \label{fig_<>}
\end{figure}
            ]],
			{
				c(1, {
					sn(
						1,
						fmta(
							[[
            [scale=<>]
            ]],
							i(1)
						)
					),
					t(""),
				}),
				i(2),
				i(3),
				i(4),
			}
		)
	),
	s(
		",I",
		fmta(
			[[
    \begin{itemize}
        \item <>
    \end{itemize}
    ]],
			{ i(1) }
		)
	),
	s(
		",nb",
		fmta(
			[[
    \begin{nicebox}{<>}
        <>
    \end{nicebox}
    ]],
			{ i(1), i(2) }
		)
	),
	s(",py", fmta([[\pyinline{<>}]], { i(1) })),
	s(
		",pY",
		fmta([[\pyfile<>{<>}]], {
			c(1, {
				fmta(
					[[
    [firstline=<>, lastline=<>]
    ]],
					{ i(1), i(2) }
				),
				t(""),
			}),
			i(2),
		})
	),
	s(
		",py",
		fmta(
			[[
          \begin{py}
          <>
          \end{py}
        ]],
			{ i(1) }
		)
	),
	s(
		",C",
		fmta(
			[[
        \begin{cases}
            <> & <>
        \end{cases}
        ]],
			{ i(1), i(2) }
		)
	),
}

-- no stylua so that entries stay single-line and can be sorted more easily, to avoid duplication/overwriting
-- stylua: ignore start
local dot = {
	s(".a", fmta([[\alpha]], {}), { condition = tex_utils.in_mathzone }),
	s(".b", fmta([[\beta]], {}), { condition = tex_utils.in_mathzone }),
	s(".d", fmta([[\delta]], {}), { condition = tex_utils.in_mathzone }),
	s(".D", fmta([[\Delta]], {}), { condition = tex_utils.in_mathzone }),
	s(".e", fmta([[\epsilon]], {}), { condition = tex_utils.in_mathzone }),
	s(".E", fmta([[\eta]], {}), { condition = tex_utils.in_mathzone }),
	s(".g", fmta([[\gamma]], {}), { condition = tex_utils.in_mathzone }),
	s(".h", fmta([[\phi]], {}), { condition = tex_utils.in_mathzone }),
	s(".H", fmta([[\Phi]], {}), { condition = tex_utils.in_mathzone }),
	s(".k", fmta([[\kappa]], {}), { condition = tex_utils.in_mathzone }),
	s(".l", fmta([[\lambda]], {}), { condition = tex_utils.in_mathzone }),
	s(".L", fmta([[\Lambda]], {}), { condition = tex_utils.in_mathzone }),
	s(".m", fmta([[\mu]], {}), { condition = tex_utils.in_mathzone }),
	s(".n", fmta([[\nu]], {}), { condition = tex_utils.in_mathzone }),
	s(".o", fmta([[\omega]], {}), { condition = tex_utils.in_mathzone }),
	s(".O", fmta([[\Omega]], {}), { condition = tex_utils.in_mathzone }),
	s(".p", fmta([[\pi]], {}), { condition = tex_utils.in_mathzone }),
	s(".P", fmta([[\Pi]], {}), { condition = tex_utils.in_mathzone }),
	s(".r", fmta([[\rho]], {}), { condition = tex_utils.in_mathzone }),
	s(".s", fmta([[\sigma]], {}), { condition = tex_utils.in_mathzone }),
	s(".S", fmta([[\Sigma]], {}), { condition = tex_utils.in_mathzone }),
	s(".t", fmta([[\tau]], {}), { condition = tex_utils.in_mathzone }),
	s(".T", fmta([[\theta]], {}), { condition = tex_utils.in_mathzone }),
-- stylua: ignore end
}

-- The snippets which use brackets in their trigger will have their closing bracket completed
-- by mini.nvim

local comma = {
	s({ trig = ",(", wordTrig = false }, fmta([[\left ( <> \right ]], { i(1) }), { condition = tex_utils.in_mathzone }),
	s({ trig = ",*", wordTrig = false }, fmta([[\times ]], {}), { condition = tex_utils.in_mathzone }),
	s({ trig = ",->", wordTrig = false }, fmta([[\longrightarrow ]], {}), { condition = tex_utils.in_mathzone }),
	s({ trig = ",..", wordTrig = false }, fmta([[\ldots ]], {}), { condition = tex_utils.in_mathzone }),
	s({ trig = ",2", wordTrig = false }, fmta([[\sqrt{<>}]], { i(1) }), { condition = tex_utils.in_mathzone }),
	s({ trig = ",,", wordTrig = false }, fmta("$ <> $<>", { i(1), i(2) })),
	s({ trig = ",<-", wordTrig = false }, fmta([[\leftarrow ]], {}), { condition = tex_utils.in_mathzone }),
	s({ trig = ",<<", wordTrig = false }, fmta([[\langle ]], {}), { condition = tex_utils.in_mathzone }),
	s({ trig = ",<>", wordTrig = false }, fmta([[\left\langle <> \right\rangle<>]], {i(1), i(2)}), { condition = tex_utils.in_mathzone }),
	s({ trig = ",==", wordTrig = false }, t([[\equiv ]]), { condition = tex_utils.in_mathzone }),
	s({ trig = ",=>", wordTrig = false }, fmta([[\implies ]], {}), { condition = tex_utils.in_mathzone }),
	s({ trig = ",>>", wordTrig = false }, fmta([[\rangle ]], {}), { condition = tex_utils.in_mathzone }),
	s({ trig = ",B", wordTrig = false }, fmta([[\bar{<>}]], { i(1) }), { condition = tex_utils.in_mathzone }),
	s({ trig = ",D", wordTrig = false }, fmta([[\cdot ]], {}), { condition = tex_utils.in_mathzone }),
	s({ trig = ",L", wordTrig = false }, fmta([[\label{<>}]], { i(1) })),
	s({ trig = ",N", wordTrig = false }, { d(1, nn_dynamic) }),
	s({ trig = ",O", wordTrig = false }, fmta([[\Ocal \left( <> \right) ]], { i(1) }), { condition = tex_utils.in_mathzone }),
	s({ trig = ",P", wordTrig = false }, fmta([[\paragraph{<>}]], { i(1) })),
	s({ trig = ",Q", wordTrig = false }, fmta([[\ , \quad ]], {}), { condition = tex_utils.in_mathzone }),
	s({ trig = ",R", wordTrig = false }, fmta([[\ref{<>}]], { i(1) })),
	s({ trig = ",SS", wordTrig = false }, fmta([[\subsubsection{<>}]], { i(1) })),
	s({ trig = ",Ss", wordTrig = false }, fmta([[\subsection{<>}]], { i(1) })),
	s({ trig = ",[", wordTrig = false }, fmta([[\left [ <> \right ]], { i(1) }), { condition = tex_utils.in_mathzone }),
	s({ trig = ",b", wordTrig = false }, { d(1, bb_dynamic) }),
	s({ trig = ",c", wordTrig = false }, fmta([[\cite{<>}]], { i(1) })),
	s({ trig = ",d", wordTrig = false }, fmta("_{ <> }<>", { i(1), i(2) }), { condition = tex_utils.in_mathzone }),
	s({ trig = ",e", wordTrig = false }, fmta("e^{ <> }<>", { i(1), i(2) }), { condition = tex_utils.in_mathzone }),
	s({ trig = ",\\", wordTrig = false }, fmta("\\frac{ <> }{ <> }", { i(1), i(2) }), { condition = tex_utils.in_mathzone }),
	s({ trig = ",hr", wordTrig = false }, fmta([[\href{<>}{<>}]], { i(1, "url"), i(2, "desc") })),
	s({ trig = ",i", wordTrig = false }, fmta([[\textit{<>}<>]], { i(1), i(2) })),
	s({ trig = ",ll", wordTrig = false }, fmta([[\left ]], {}), { condition = tex_utils.in_mathzone }),
	s({ trig = ",m", wordTrig = false }, fmta([[\mathcal{<>}<>]], { i(1), i(2) }), { condition = tex_utils.in_mathzone }),
	s({ trig = ",pd", wordTrig = false }, fmta([[\partial ]], {}), { condition = tex_utils.in_mathzone }),
	s({ trig = ",q", wordTrig = false }, fmta([[\eqref{<>}<>]], { i(1), i(2) })),
	s({ trig = ",rA", wordTrig = false }, fmta([[App.~\ref{<>}<>]], { i(1), i(2) })),
	s({ trig = ",rF", wordTrig = false }, fmta([[Foot.~\ref{<>}<>]], { i(1), i(2) })),
	s({ trig = ",rf", wordTrig = false }, fmta([[Fig.~\ref{<>}<>]], { i(1), i(2) })),
	s({ trig = ",rm", wordTrig = false }, fmta([[{\rm <>}<>]], { i(1), i(2) })),
	s({ trig = ",rr", wordTrig = false }, fmta([[\right <>]], { i(1) }), { condition = tex_utils.in_mathzone }),
	s({ trig = ",rs", wordTrig = false }, fmta([[Sec.~\ref{<>}<>]], { i(1), i(2) })),
	s({ trig = ",s", wordTrig = false }, fmta([[\section{<>}<>]], { i(1), i(2) })),
	s({ trig = ",t", wordTrig = false }, fmta([[\texttt{<>}<>]], { i(1), i(2) })),
	s({ trig = ",u", wordTrig = false }, fmta("^{ <> }<>", { i(1), i(2) }), { condition = tex_utils.in_mathzone }),
	s({ trig = ",{", wordTrig = false }, fmta([[\left \{ <> \right \]], { i(1) }), { condition = tex_utils.in_mathzone }),
	s({ trig = ",~=", wordTrig = false }, fmta([[\approx ]], {}), { condition = tex_utils.in_mathzone }),
	s({ trig = ",~~", wordTrig = false }, fmta([[\sim ]], {}), { condition = tex_utils.in_mathzone }),
	s({ trig = ",fn", wordTrig = false }, fmta([[\footnote{<>}]], { i(1) })),
}
-- stylua: ignore end

local collection = { dot, env, comma }

for _, snip in pairs(collection) do
	autosnippets = vim.list_extend(autosnippets, snip)
end

return snippets, autosnippets
