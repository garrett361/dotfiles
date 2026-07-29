local prequire = require("nvim_utils").prequire

-- rustaceanvim is configured through vim.g, not setup(), and the value has to be in place
-- before its ftplugin runs. A function defers evaluation to that point, so requiring
-- cmp_nvim_lsp here cannot race lazy.nvim's load order.
local function init()
	vim.g.rustaceanvim = function()
		return {
			server = {
				-- Kept in sync by hand with the capabilities in lua/user/lsp/init.lua, whose
				-- local is file-scoped. rustaceanvim deep-merges this over its own
				-- create_client_capabilities(), so its experimental capabilities survive.
				capabilities = prequire("cmp_nvim_lsp").default_capabilities(),
				on_attach = function(client, bufnr)
					if client.server_capabilities.inlayHintProvider then
						vim.g.inlay_hints_visible = true
						vim.lsp.inlay_hint.enable(true, { bufnr = bufnr })
					end
				end,
			},
			-- nvim-dap-lldb already populates dap.configurations.rust with cargo-aware
			-- entries, which is what <A-d> uses. Without this, rustaceanvim appends a second
			-- set on attach and the picker shows both.
			dap = { autoload_configurations = false },
		}
	end
end

return {
	"mrcjkb/rustaceanvim",
	-- v9 dropped nvim 0.11; ^8 was only the bridge while this config was still on it.
	version = "^9",
	lazy = false,
	init = init,
}
