local ls = require("nvim_utils").prequire("luasnip")

-- Helper objects, following the docs.
local s = ls.snippet
local t = ls.text_node

local snippets, autosnippets = {}, {}

local gg_note = s(",N", t("NOTE: @goon - "))
table.insert(autosnippets, gg_note)

local gg_todo = s(",T", t("TODO: @goon - "))
table.insert(autosnippets, gg_todo)

local gg_del = s(",D", t("TODO: @goon - DELETE"))
table.insert(autosnippets, gg_del)

local gg_hack = s(",H", t("HACK: @goon - "))
table.insert(autosnippets, gg_hack)

return snippets, autosnippets
