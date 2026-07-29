local ls = require("nvim_utils").prequire("luasnip")

-- Helper objects, following the docs.
local s = ls.snippet
local fmta = require("luasnip.extras.fmt").fmta

local snippets, autosnippets = {}, {}

local shebang = s(",!", fmta([[#!/usr/bin/env bash ]], {}))
table.insert(autosnippets, shebang)

return snippets, autosnippets
