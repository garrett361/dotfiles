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

local gg_note = s("GN", t("NOTE: @goon - "))
table.insert(autosnippets, gg_note)

local gg_todo = s("GT", t("TODO: @goon - "))
table.insert(autosnippets, gg_todo)

local gg_del = s("GD", t("TODO: @goon - DELETE"))
table.insert(autosnippets, gg_del)

local gg_hack = s("GH", t("HACK: @goon - "))
table.insert(autosnippets, gg_hack)

return snippets, autosnippets
