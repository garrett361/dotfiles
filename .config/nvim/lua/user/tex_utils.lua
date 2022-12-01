-- From https://www.ejmastnak.com/tutorials/vim-latex/luasnip/#context-specific-expansion-for-latex
local tex_utils = {}
-- HACK: Temporarily having in_mathzone return true always, because the underlying in_mathzone method
-- doesn't work in included files which don't have a \begin{document} in them.
-- https://github.com/lervag/vimtex/issues/3037
tex_utils.in_mathzone = function() -- math context detection
	-- return vim.fn["vimtex#syntax#in_mathzone"]() == 1
	return true
end
tex_utils.in_text = function()
	return not tex_utils.in_mathzone()
end
tex_utils.in_comment = function() -- comment detection
	return vim.fn["vimtex#syntax#in_comment"]() == 1
end
tex_utils.in_env = function(name) -- generic environment detection
	local is_inside = vim.fn["vimtex#env#is_inside"](name)
	return (is_inside[1] > 0 and is_inside[2] > 0)
end
-- A few concrete environments---adapt as needed
tex_utils.in_equation = function() -- equation environment detection
	return tex_utils.in_env("equation")
end
tex_utils.in_align = function() -- equation environment detection
	return tex_utils.in_env("align")
end
tex_utils.in_itemize = function() -- itemize environment detection
	return tex_utils.in_env("itemize")
end
tex_utils.in_enumerate = function() -- itemize environment detection
	return tex_utils.in_env("enumerate")
end
tex_utils.in_tikz = function() -- TikZ picture environment detection
	return tex_utils.in_env("tikzpicture")
end
return tex_utils
