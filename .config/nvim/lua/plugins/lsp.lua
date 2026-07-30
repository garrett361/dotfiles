require("nvim_utils").prequire("user.lsp")

-- No plugin spec: nvim 0.12 configures LSP natively and mason is gone, so this file exists only to
-- load user.lsp at spec-import time, before the first FileType autocmd fires. It stays under
-- plugins/ because nvim_min symlinks that directory per file and so never sees it, whereas
-- init.lua and user/keymaps.lua are shared.
return {}
